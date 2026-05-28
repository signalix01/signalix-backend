# Celery Worker Guide for Backtesting

## Overview

This guide explains how to run Celery workers for async backtest execution.

## Prerequisites

1. Redis server running (for broker and result backend)
2. PostgreSQL database configured
3. Python environment with all dependencies installed

## Starting Redis

### Local Development (Docker)

```bash
docker run -d -p 6379:6379 redis:7-alpine
```

### Check Redis Connection

```bash
redis-cli ping
# Should return: PONG
```

## Starting Celery Worker

### Basic Worker

```bash
cd signalixai-backend
celery -A services.backtesting.celery_app worker --loglevel=info
```

### Production Worker (with concurrency)

```bash
celery -A services.backtesting.celery_app worker \
  --loglevel=info \
  --concurrency=4 \
  --queue=backtesting \
  --max-tasks-per-child=50
```

### Worker Options

- `--loglevel`: Logging level (debug/info/warning/error)
- `--concurrency`: Number of worker processes (default: CPU count)
- `--queue`: Queue name to consume from
- `--max-tasks-per-child`: Restart worker after N tasks (memory cleanup)
- `--autoscale`: Auto-scale workers (e.g., `--autoscale=10,3` for 3-10 workers)

## Monitoring with Flower

Flower is a web-based monitoring tool for Celery.

### Install Flower

```bash
pip install flower
```

### Start Flower

```bash
celery -A services.backtesting.celery_app flower
```

Access at: http://localhost:5555

### Flower Features

- Real-time task monitoring
- Worker status and statistics
- Task history and results
- Task rate limiting
- Worker pool management

## Production Deployment

### Systemd Service (Linux)

Create `/etc/systemd/system/celery-backtest.service`:

```ini
[Unit]
Description=Celery Worker for Backtesting
After=network.target redis.target postgresql.target

[Service]
Type=forking
User=www-data
Group=www-data
WorkingDirectory=/opt/signalixai-backend
Environment="PATH=/opt/signalixai-backend/venv/bin"
ExecStart=/opt/signalixai-backend/venv/bin/celery -A services.backtesting.celery_app worker \
  --loglevel=info \
  --concurrency=4 \
  --queue=backtesting \
  --pidfile=/var/run/celery-backtest.pid \
  --logfile=/var/log/celery-backtest.log
ExecStop=/bin/kill -s TERM $MAINPID
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable celery-backtest
sudo systemctl start celery-backtest
sudo systemctl status celery-backtest
```

### Docker Compose

Add to `docker-compose.yml`:

```yaml
services:
  celery-worker:
    build: .
    command: celery -A services.backtesting.celery_app worker --loglevel=info --concurrency=4
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/1
      - CELERY_RESULT_BACKEND=redis://redis:6379/2
      - DATABASE_URL=postgresql://user:pass@postgres:5432/signalixai
    depends_on:
      - redis
      - postgres
    restart: always
    
  celery-flower:
    build: .
    command: celery -A services.backtesting.celery_app flower
    ports:
      - "5555:5555"
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/1
      - CELERY_RESULT_BACKEND=redis://redis:6379/2
    depends_on:
      - redis
    restart: always
```

### AWS ECS (Elastic Container Service)

Task definition for auto-scaling workers:

```json
{
  "family": "celery-backtest-worker",
  "containerDefinitions": [
    {
      "name": "worker",
      "image": "signalixai-backend:latest",
      "command": [
        "celery",
        "-A",
        "services.backtesting.celery_app",
        "worker",
        "--loglevel=info",
        "--concurrency=4"
      ],
      "environment": [
        {
          "name": "CELERY_BROKER_URL",
          "value": "redis://redis.example.com:6379/1"
        },
        {
          "name": "CELERY_RESULT_BACKEND",
          "value": "redis://redis.example.com:6379/2"
        }
      ],
      "memory": 2048,
      "cpu": 1024
    }
  ]
}
```

Auto-scaling policy based on queue depth:
- Scale out when queue depth > 5
- Scale in when queue depth < 2
- Min workers: 2
- Max workers: 20

## Monitoring and Debugging

### Check Worker Status

```bash
celery -A services.backtesting.celery_app inspect active
celery -A services.backtesting.celery_app inspect stats
celery -A services.backtesting.celery_app inspect registered
```

### Check Queue Length

```bash
redis-cli llen celery
```

### View Task Results

```bash
redis-cli keys "celery-task-meta-*"
redis-cli get "celery-task-meta-<task-id>"
```

### Purge Queue (Development Only)

```bash
celery -A services.backtesting.celery_app purge
```

## Performance Tuning

### Worker Concurrency

- **CPU-bound tasks**: Set concurrency = CPU cores
- **I/O-bound tasks**: Set concurrency = 2-4x CPU cores
- **Mixed workload**: Start with CPU cores, monitor and adjust

### Prefetch Multiplier

- Default: 4 (worker prefetches 4 tasks)
- For long-running tasks: Set to 1 (prevents task hoarding)
- For short tasks: Keep default or increase

### Task Time Limits

- Soft limit: 25 minutes (raises exception)
- Hard limit: 30 minutes (kills worker)
- Adjust based on typical backtest duration

### Memory Management

- `--max-tasks-per-child=50`: Restart worker after 50 tasks
- Prevents memory leaks from accumulating
- Adjust based on memory usage patterns

## Troubleshooting

### Worker Not Starting

1. Check Redis connection:
   ```bash
   redis-cli ping
   ```

2. Check environment variables:
   ```bash
   echo $CELERY_BROKER_URL
   echo $CELERY_RESULT_BACKEND
   ```

3. Check logs:
   ```bash
   celery -A services.backtesting.celery_app worker --loglevel=debug
   ```

### Tasks Not Executing

1. Check task is registered:
   ```bash
   celery -A services.backtesting.celery_app inspect registered
   ```

2. Check queue:
   ```bash
   redis-cli llen celery
   ```

3. Check worker is consuming:
   ```bash
   celery -A services.backtesting.celery_app inspect active
   ```

### High Memory Usage

1. Reduce concurrency
2. Lower `--max-tasks-per-child`
3. Check for memory leaks in task code
4. Monitor with Flower

### Slow Task Execution

1. Check data pipeline performance
2. Verify database connection pooling
3. Monitor Redis latency
4. Check worker CPU/memory usage

## Best Practices

1. **Always use task time limits** to prevent runaway tasks
2. **Monitor queue depth** and scale workers accordingly
3. **Use Flower** for production monitoring
4. **Set up alerts** for failed tasks and high queue depth
5. **Log task progress** for debugging
6. **Use task retries** for transient failures
7. **Separate queues** for different task priorities
8. **Regular worker restarts** to prevent memory leaks

## Environment Variables

Required environment variables:

```bash
# Celery
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/signalixai

# Redis
REDIS_URL=redis://localhost:6379/0

# Optional
CELERY_TASK_TIME_LIMIT=1800
CELERY_TASK_SOFT_TIME_LIMIT=1500
CELERY_WORKER_PREFETCH_MULTIPLIER=1
```

## Testing

### Test Task Submission

```python
from services.backtesting.tasks import run_backtest_task
from services.backtesting.models import BacktestConfig

# Submit task
task = run_backtest_task.delay(config.json(), backtest_id, user_id)

# Check status
print(task.state)
print(task.info)

# Get result (blocks until complete)
result = task.get(timeout=300)
```

### Test with Synchronous Execution

For testing without Celery:

```python
from services.backtesting.tasks import run_backtest_sync

backtest_id = run_backtest_sync(config, user_id="test-user")
```

## Support

For issues or questions:
1. Check logs: `/var/log/celery-backtest.log`
2. Monitor Flower: http://localhost:5555
3. Check Redis: `redis-cli monitor`
4. Review task code: `services/backtesting/tasks.py`
