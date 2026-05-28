"""
Webhook Queue

Redis-based webhook queue with FIFO ordering and priority support.
Requirements: 49.1, 49.2, 49.3, 49.4, 49.8, 49.9
"""

import json
import uuid
import logging
from enum import Enum
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class QueuePriority(int, Enum):
    """Webhook processing priority levels"""
    CRITICAL = 1    # Immediate execution
    HIGH = 2        # Execute ASAP
    NORMAL = 3      # Standard queue
    LOW = 4         # Background processing


@dataclass
class WebhookJob:
    """Webhook job for queue processing"""
    id: str
    user_id: str
    integration_type: str
    payload: Dict[str, Any]
    headers: Dict[str, str]
    source_ip: str
    priority: QueuePriority
    created_at: datetime
    retry_count: int = 0
    max_retries: int = 3
    webhook_config_id: Optional[str] = None
    log_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "integration_type": self.integration_type,
            "payload": self.payload,
            "headers": self.headers,
            "source_ip": self.source_ip,
            "priority": self.priority.value,
            "created_at": self.created_at.isoformat(),
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "webhook_config_id": self.webhook_config_id,
            "log_id": self.log_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WebhookJob":
        """Create from dictionary"""
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            integration_type=data["integration_type"],
            payload=data["payload"],
            headers=data.get("headers", {}),
            source_ip=data.get("source_ip", ""),
            priority=QueuePriority(data.get("priority", 3)),
            created_at=datetime.fromisoformat(data["created_at"]),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            webhook_config_id=data.get("webhook_config_id"),
            log_id=data.get("log_id")
        )


class WebhookQueue:
    """
    Redis-based webhook queue with priority support
    
    Features:
    - FIFO ordering within priority levels
    - Priority queuing for time-sensitive webhooks
    - Worker pool for parallel processing
    - Dead letter queue for failed jobs
    
    Requirements: 49.1, 49.2, 49.3, 49.4
    """
    
    # Redis keys
    QUEUE_PREFIX = "webhook:queue"
    PROCESSING_PREFIX = "webhook:processing"
    DEAD_LETTER_KEY = "webhook:dead_letter"
    METRICS_KEY = "webhook:metrics"
    
    def __init__(self, redis_client=None, worker_count: int = 4):
        """
        Initialize webhook queue
        
        Args:
            redis_client: Redis client instance
            worker_count: Number of worker threads for parallel processing
        """
        self.redis = redis_client
        self.worker_count = worker_count
        self.logger = logging.getLogger(self.__class__.__name__)
        self.executor = ThreadPoolExecutor(max_workers=worker_count)
        self._running = False
        self._worker_tasks = []
    
    def _get_queue_key(self, priority: QueuePriority) -> str:
        """Get Redis key for priority queue"""
        return f"{self.QUEUE_PREFIX}:priority:{priority.value}"
    
    async def enqueue(
        self,
        job: WebhookJob
    ) -> bool:
        """
        Add job to queue
        
        Args:
            job: Webhook job to enqueue
            
        Returns:
            True if successfully enqueued
            
        Requirements: 49.1, 49.2
        """
        if not self.redis:
            self.logger.error("Redis not available")
            return False
        
        try:
            queue_key = self._get_queue_key(job.priority)
            
            # Use timestamp as score for FIFO ordering within priority
            score = job.created_at.timestamp()
            
            # Add to sorted set
            await self.redis.zadd(
                queue_key,
                {json.dumps(job.to_dict()): score}
            )
            
            # Update metrics
            await self._increment_metric("enqueued")
            
            self.logger.debug(f"Enqueued job {job.id} to {queue_key}")
            return True
            
        except Exception as e:
            self.logger.error(f"Enqueue error: {str(e)}")
            return False
    
    async def dequeue(
        self,
        timeout: int = 5
    ) -> Optional[WebhookJob]:
        """
        Get next job from queue (highest priority first)
        
        Args:
            timeout: Timeout in seconds
            
        Returns:
            WebhookJob or None if queue is empty
            
        Requirements: 49.3
        """
        if not self.redis:
            return None
        
        try:
            # Try priorities in order: CRITICAL, HIGH, NORMAL, LOW
            for priority in [QueuePriority.CRITICAL, QueuePriority.HIGH, 
                           QueuePriority.NORMAL, QueuePriority.LOW]:
                queue_key = self._get_queue_key(priority)
                
                # Get and remove first item (lowest score = oldest)
                items = await self.redis.zpopmin(queue_key, count=1)
                
                if items:
                    job_data = json.loads(items[0][0])
                    job = WebhookJob.from_dict(job_data)
                    
                    # Move to processing queue
                    await self._add_to_processing(job)
                    
                    self.logger.debug(f"Dequeued job {job.id} from priority {priority.name}")
                    return job
            
            return None
            
        except Exception as e:
            self.logger.error(f"Dequeue error: {str(e)}")
            return None
    
    async def _add_to_processing(self, job: WebhookJob):
        """Add job to processing queue"""
        processing_key = f"{self.PROCESSING_PREFIX}:{job.id}"
        await self.redis.setex(
            processing_key,
            300,  # 5 minute TTL
            json.dumps(job.to_dict())
        )
    
    async def mark_completed(self, job_id: str):
        """Mark job as completed"""
        if not self.redis:
            return
        
        try:
            # Remove from processing queue
            processing_key = f"{self.PROCESSING_PREFIX}:{job_id}"
            await self.redis.delete(processing_key)
            
            # Update metrics
            await self._increment_metric("completed")
            
        except Exception as e:
            self.logger.error(f"Mark completed error: {str(e)}")
    
    async def mark_failed(
        self,
        job: WebhookJob,
        error_message: str
    ) -> bool:
        """
        Mark job as failed and retry or move to dead letter
        
        Args:
            job: Failed job
            error_message: Error description
            
        Returns:
            True if job was retried, False if moved to dead letter
            
        Requirements: 49.8, 49.9
        """
        if not self.redis:
            return False
        
        try:
            # Remove from processing
            processing_key = f"{self.PROCESSING_PREFIX}:{job.id}"
            await self.redis.delete(processing_key)
            
            # Check if we should retry
            if job.retry_count < job.max_retries:
                job.retry_count += 1
                
                # Exponential backoff delay
                delay_seconds = 2 ** job.retry_count
                job.created_at = datetime.utcnow()
                
                # Re-queue with delay
                await asyncio.sleep(delay_seconds)
                await self.enqueue(job)
                
                await self._increment_metric("retried")
                self.logger.info(f"Retrying job {job.id} (attempt {job.retry_count})")
                return True
            else:
                # Move to dead letter queue
                await self._move_to_dead_letter(job, error_message)
                return False
                
        except Exception as e:
            self.logger.error(f"Mark failed error: {str(e)}")
            return False
    
    async def _move_to_dead_letter(
        self,
        job: WebhookJob,
        error_message: str
    ):
        """Move job to dead letter queue"""
        try:
            dead_letter_entry = {
                "job": job.to_dict(),
                "error": error_message,
                "failed_at": datetime.utcnow().isoformat(),
                "retry_count": job.retry_count
            }
            
            await self.redis.lpush(
                self.DEAD_LETTER_KEY,
                json.dumps(dead_letter_entry)
            )
            
            # Trim dead letter queue (keep last 1000)
            await self.redis.ltrim(self.DEAD_LETTER_KEY, 0, 999)
            
            await self._increment_metric("dead_letter")
            self.logger.warning(f"Job {job.id} moved to dead letter queue")
            
        except Exception as e:
            self.logger.error(f"Dead letter error: {str(e)}")
    
    async def get_queue_depth(self) -> Dict[str, int]:
        """Get current queue depth by priority"""
        if not self.redis:
            return {}
        
        depths = {}
        for priority in QueuePriority:
            queue_key = self._get_queue_key(priority)
            count = await self.redis.zcard(queue_key)
            depths[priority.name] = count
        
        depths["total"] = sum(depths.values())
        return depths
    
    async def get_processing_count(self) -> int:
        """Get number of jobs currently being processed"""
        if not self.redis:
            return 0
        
        try:
            pattern = f"{self.PROCESSING_PREFIX}:*"
            keys = await self.redis.keys(pattern)
            return len(keys)
        except Exception as e:
            self.logger.error(f"Get processing count error: {str(e)}")
            return 0
    
    async def get_dead_letter_count(self) -> int:
        """Get number of jobs in dead letter queue"""
        if not self.redis:
            return 0
        
        try:
            return await self.redis.llen(self.DEAD_LETTER_KEY)
        except Exception as e:
            self.logger.error(f"Get dead letter count error: {str(e)}")
            return 0
    
    async def get_dead_letter_jobs(
        self,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get jobs from dead letter queue"""
        if not self.redis:
            return []
        
        try:
            items = await self.redis.lrange(self.DEAD_LETTER_KEY, 0, limit - 1)
            return [json.loads(item) for item in items]
        except Exception as e:
            self.logger.error(f"Get dead letter jobs error: {str(e)}")
            return []
    
    async def replay_dead_letter_job(self, job_id: str) -> bool:
        """
        Replay a job from dead letter queue
        
        Args:
            job_id: ID of job to replay
            
        Returns:
            True if job was found and replayed
        """
        if not self.redis:
            return False
        
        try:
            # Get all dead letter jobs
            items = await self.redis.lrange(self.DEAD_LETTER_KEY, 0, -1)
            
            for item in items:
                entry = json.loads(item)
                if entry["job"]["id"] == job_id:
                    # Remove from dead letter
                    await self.redis.lrem(self.DEAD_LETTER_KEY, 0, item)
                    
                    # Reset retry count and re-queue
                    job = WebhookJob.from_dict(entry["job"])
                    job.retry_count = 0
                    job.created_at = datetime.utcnow()
                    
                    await self.enqueue(job)
                    
                    self.logger.info(f"Replaying dead letter job {job_id}")
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Replay dead letter error: {str(e)}")
            return False
    
    async def _increment_metric(self, metric_name: str):
        """Increment a metric counter"""
        if not self.redis:
            return
        
        try:
            key = f"{self.METRICS_KEY}:{metric_name}"
            await self.redis.incr(key)
            # Set expiry on metric (keep for 24 hours)
            await self.redis.expire(key, 86400)
        except Exception:
            pass
    
    async def get_metrics(self) -> Dict[str, int]:
        """Get queue metrics"""
        if not self.redis:
            return {}
        
        try:
            metric_names = ["enqueued", "completed", "retried", "dead_letter"]
            metrics = {}
            
            for name in metric_names:
                key = f"{self.METRICS_KEY}:{name}"
                value = await self.redis.get(key)
                metrics[name] = int(value) if value else 0
            
            return metrics
        except Exception as e:
            self.logger.error(f"Get metrics error: {str(e)}")
            return {}
    
    async def purge_queue(self, priority: Optional[QueuePriority] = None) -> int:
        """
        Purge jobs from queue
        
        Args:
            priority: Specific priority to purge, or all if None
            
        Returns:
            Number of jobs purged
        """
        if not self.redis:
            return 0
        
        try:
            if priority:
                queue_key = self._get_queue_key(priority)
                count = await self.redis.zcard(queue_key)
                await self.redis.delete(queue_key)
                return count
            else:
                total = 0
                for p in QueuePriority:
                    queue_key = self._get_queue_key(p)
                    count = await self.redis.zcard(queue_key)
                    await self.redis.delete(queue_key)
                    total += count
                return total
        except Exception as e:
            self.logger.error(f"Purge queue error: {str(e)}")
            return 0
