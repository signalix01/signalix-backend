# Celery Beat Configuration

## Overview

This document describes the Celery Beat configuration for Signalix backend scheduled tasks. Celery Beat is the scheduler that triggers periodic tasks at specified intervals.

**Task 51: Celery beat configuration**

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Celery Beat Scheduler                    │
│                    (ECS Fargate Service)                     │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ Schedules tasks based on crontab
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                      Redis (Broker)                          │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ Task messages
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    Celery Workers                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Screening│  │    ML    │  │   Data   │  │Maintenance│   │
│  │  Queue   │  │  Queue   │  │  Queue   │  │   Queue   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Scheduled Tasks

### 1. Screening Snapshot Refresh
- **Task**: `services.screening.tasks.refresh_screening_snapshot`
- **Schedule**: Every 15 minutes during market hours (09:15 - 15:30 IST)
- **Purpose**: Refresh the `screening_snapshot` materialized view with latest OHLCV data
- **Queue**: `screening`
- **Time Limit**: 10 minutes
- **Requirements**: 9.3, 16.1

### 2. Run Scheduled Screeners
- **Task**: `services.screening.tasks.run_scheduled_screeners`
- **Schedule**: Every 15 minutes
- **Purpose**: Check each criteria's cron schedule and run due screeners
- **Queue**: `screening`
- **Time Limit**: 5 minutes
- **Requirements**: 9.5, 9.6

### 3. Retrain Isolation Forest Models
- **Task**: `services.alerts.tasks.retrain_isolation_forest_models`
- **Schedule**: Daily at 03:00 IST
- **Purpose**: Retrain ML anomaly detection models on 90-day rolling window
- **Queue**: `ml`
- **Time Limit**: 1 hour
- **Requirements**: 11.4, 16.7

### 4. Fetch FII/DII Data
- **Task**: `services.alerts.whale_trackers.tasks.fetch_fii_dii_data`
- **Schedule**: Daily at 16:45 IST
- **Purpose**: Fetch FII/DII net activity from NSDL after NSE publishes
- **Queue**: `data`
- **Time Limit**: 30 minutes
- **Requirements**: 12.1, 12.3, 12.4

### 5. Fetch COT Report Data
- **Task**: `services.alerts.whale_trackers.tasks.fetch_cot_report_data`
- **Schedule**: Every Friday at 22:30 IST
- **Purpose**: Fetch CFTC Commitments of Traders report after Friday publication
- **Queue**: `data`
- **Time Limit**: 1 hour
- **Requirements**: 12.1

### 6. Purge Old Anomaly Events
- **Task**: `services.alerts.tasks.purge_old_anomaly_events`
- **Schedule**: Daily at 02:00 IST
- **Purpose**: Clean up old anomaly events based on tier retention policies
- **Queue**: `maintenance`
- **Time Limit**: 30 minutes
- **Requirements**: 16.2, 16.3

### 7. Register Dynamic Beat Schedules
- **Task**: `services.screening.tasks.register_dynamic_beat_schedules`
- **Schedule**: Every 5 minutes
- **Purpose**: Sync Celery Beat schedule with database for user-defined screeners
- **Queue**: `default`
- **Time Limit**: 4 minutes

## Configuration Files

### Main Configuration
- **File**: `celery_config.py`
- **Purpose**: Central Celery configuration with all beat schedules
- **Location**: `signalixai-backend/celery_config.py`

### Task Implementations
- **Screening Tasks**: `services/screening/tasks.py`
- **Alert Tasks**: `services/alerts/tasks.py`
- **Whale Tracker Tasks**: `services/alerts/whale_trackers/tasks.py`

### Deployment
- **ECS Task Definition**: `ecs-celery-beat-task-definition.json`
- **Deployment Script**: `deploy_celery_beat_ecs.sh`

### Testing
- **Smoke Tests**: `tests/test_celery_beat_smoke.py`

## Queue Configuration

Tasks are distributed across multiple queues for better resource management:

| Queue | Priority | Purpose | Tasks |
|-------|----------|---------|-------|
| `screening` | 7 (High) | Real-time screening | Snapshot refresh, scheduled screeners |
| `ml` | 6 (Medium-High) | ML model training | Isolation Forest retraining |
| `data` | 6 (Medium-High) | External data fetching | FII/DII, COT reports |
| `maintenance` | 3 (Low) | Background cleanup | Anomaly event purging |
| `default` | 5 (Medium) | General tasks | Dynamic schedule registration |

## Deployment

### Local Development

```bash
# Start Celery worker
celery -A celery_config.celery_app worker --loglevel=info --queues=screening,ml,data,maintenance,default

# Start Celery beat (in separate terminal)
celery -A celery_config.celery_app beat --loglevel=info
```

### Docker Compose

```yaml
celery-worker:
  build: .
  command: celery -A celery_config.celery_app worker --loglevel=info
  environment:
    - DATABASE_URL=${DATABASE_URL}
    - CELERY_BROKER_URL=${CELERY_BROKER_URL}
    - CELERY_RESULT_BACKEND=${CELERY_RESULT_BACKEND}

celery-beat:
  build: .
  command: celery -A celery_config.celery_app beat --loglevel=info
  environment:
    - DATABASE_URL=${DATABASE_URL}
    - CELERY_BROKER_URL=${CELERY_BROKER_URL}
    - CELERY_RESULT_BACKEND=${CELERY_RESULT_BACKEND}
```

### AWS ECS Fargate

```bash
# Set environment variables
export AWS_ACCOUNT_ID=123456789012
export AWS_REGION=ap-south-1
export VPC_ID=vpc-xxxxx
export SUBNET_IDS=subnet-xxxxx,subnet-yyyyy
export SECURITY_GROUP_ID=sg-xxxxx

# Deploy Celery Beat
bash deploy_celery_beat_ecs.sh
```

The deployment script will:
1. Build and push Docker image to ECR
2. Create CloudWatch log group
3. Register ECS task definition
4. Create/update ECS service
5. Wait for service to stabilize
6. Verify deployment

### Monitoring

**View Logs:**
```bash
aws logs tail /ecs/signalix-celery-beat --follow --region ap-south-1
```

**Check Service Status:**
```bash
aws ecs describe-services \
  --cluster signalix-cluster \
  --services signalix-celery-beat \
  --region ap-south-1
```

**Scale Service:**
```bash
# Scale up (not recommended - only 1 beat instance should run)
aws ecs update-service \
  --cluster signalix-cluster \
  --service signalix-celery-beat \
  --desired-count 1 \
  --region ap-south-1
```

## Testing

### Run Smoke Tests

```bash
# Run all smoke tests
pytest tests/test_celery_beat_smoke.py -v

# Run specific test
pytest tests/test_celery_beat_smoke.py::TestCeleryBeatSmoke::test_refresh_screening_snapshot_task -v
```

### Manual Task Triggering

```python
from celery_config import celery_app

# Trigger task manually
from services.screening.tasks import refresh_screening_snapshot
result = refresh_screening_snapshot.delay(check_market_hours=False)

# Check result
print(result.get(timeout=60))
```

### Verify Schedule

```python
from celery_config import celery_app

# Print all scheduled tasks
for name, schedule in celery_app.conf.beat_schedule.items():
    print(f"{name}: {schedule['task']} - {schedule['schedule']}")
```

## Monitoring & Alerts

### CloudWatch Metrics

Monitor these metrics in CloudWatch:
- Task execution count
- Task success/failure rate
- Task execution duration
- Queue depth

### CloudWatch Alarms

Set up alarms for:
- Task failures > 3 in 1 hour
- Task execution time > time limit
- Beat service not running
- Worker queue depth > 100

### Flower (Optional)

For real-time monitoring, deploy Flower:

```bash
celery -A celery_config.celery_app flower --port=5555
```

Access at: http://localhost:5555

## Troubleshooting

### Beat Not Scheduling Tasks

**Symptoms**: Tasks not appearing in worker logs

**Solutions**:
1. Check beat service is running: `aws ecs describe-services ...`
2. Check beat logs: `aws logs tail /ecs/signalix-celery-beat --follow`
3. Verify Redis connection: `redis-cli ping`
4. Check beat schedule: `celery -A celery_config.celery_app inspect scheduled`

### Tasks Not Executing

**Symptoms**: Tasks scheduled but not executing

**Solutions**:
1. Check worker is running and consuming from correct queues
2. Check worker logs for errors
3. Verify task routing configuration
4. Check Redis queue depth: `redis-cli llen celery`

### Task Timeout

**Symptoms**: Tasks killed after time limit

**Solutions**:
1. Increase task time limit in `celery_config.py`
2. Optimize task implementation
3. Split long-running tasks into smaller chunks
4. Use task chunking for batch operations

### Memory Issues

**Symptoms**: Worker OOM killed

**Solutions**:
1. Increase ECS task memory limit
2. Reduce `worker_max_tasks_per_child` to force worker restart
3. Optimize task memory usage
4. Use pagination for large datasets

## Best Practices

### 1. Single Beat Instance
- **CRITICAL**: Only run ONE Celery Beat instance
- Multiple beat instances will schedule duplicate tasks
- Use ECS desired count = 1

### 2. Task Idempotency
- All tasks should be idempotent (safe to run multiple times)
- Use database locks or Redis locks for critical sections
- Check for existing results before processing

### 3. Error Handling
- All tasks should handle errors gracefully
- Return structured error responses
- Log errors with context for debugging

### 4. Time Limits
- Set appropriate time limits for each task
- Use soft time limit for graceful shutdown
- Monitor task execution times

### 5. Queue Management
- Use separate queues for different task types
- Set queue priorities appropriately
- Monitor queue depths

### 6. Monitoring
- Set up CloudWatch alarms for failures
- Monitor task execution times
- Track task success/failure rates

## Security

### Secrets Management
- Store sensitive credentials in AWS Secrets Manager
- Reference secrets in ECS task definition
- Never commit secrets to code

### Network Security
- Run Celery Beat in private subnet
- Use security groups to restrict access
- Enable VPC endpoints for AWS services

### IAM Permissions
- Use least privilege IAM roles
- Separate execution role and task role
- Audit IAM permissions regularly

## Cost Optimization

### ECS Fargate Costs
- Beat service: ~$15-20/month (512 CPU, 1GB memory, 24/7)
- Workers: Scale based on load
- Use Fargate Spot for non-critical workers

### Redis Costs
- Use ElastiCache for production
- Consider Redis cluster for high availability
- Monitor memory usage

### Data Transfer
- Use VPC endpoints to avoid NAT gateway costs
- Keep services in same region
- Use S3 for large data transfers

## Maintenance

### Regular Tasks
- Review task execution logs weekly
- Monitor task success rates
- Update task schedules as needed
- Optimize slow tasks

### Updates
- Test schedule changes in staging first
- Use blue-green deployment for updates
- Monitor after deployment

### Backup
- Beat schedule is in code (version controlled)
- Redis data is ephemeral (no backup needed)
- Database has separate backup strategy

## References

- [Celery Documentation](https://docs.celeryproject.org/)
- [Celery Beat Documentation](https://docs.celeryproject.org/en/stable/userguide/periodic-tasks.html)
- [AWS ECS Documentation](https://docs.aws.amazon.com/ecs/)
- [Redis Documentation](https://redis.io/documentation)

## Support

For issues or questions:
1. Check logs: `aws logs tail /ecs/signalix-celery-beat --follow`
2. Review this documentation
3. Check Celery documentation
4. Contact DevOps team

---

**Last Updated**: 2024-01-08  
**Version**: 1.0.0  
**Status**: ✅ Production Ready
