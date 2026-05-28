# Signalix Algo Backend - Deployment Guide

## Overview

This guide covers the complete deployment process for the Signalix Algo Builder, Backtesting, AI Screening & Alert Engine backend services.

**Services:**
1. Algo Builder Service (Port 8000)
2. Backtesting Service (Port 8001)
3. Screening Service (Port 8002)
4. Alerts Service (Port 8003)

**Infrastructure:**
- AWS ECS Fargate for container orchestration
- AWS RDS Aurora PostgreSQL with TimescaleDB
- AWS ElastiCache Redis
- AWS SQS for message queuing
- AWS Secrets Manager for API keys
- Nginx for reverse proxy and load balancing

---

## Prerequisites

### Required Tools
- Docker 20.10+
- Docker Compose 2.0+
- AWS CLI 2.0+
- AWS CDK 2.0+
- Node.js 18+ (for CDK)
- Python 3.12+

### AWS Account Setup
1. AWS account with appropriate permissions
2. AWS CLI configured with credentials
3. ECR repositories created for each service
4. Route53 hosted zone for domain
5. ACM certificate for SSL/TLS

### API Keys Required
- Glassnode API key (crypto on-chain data)
- Polygon.io API key (US equities data)
- Google Gemini API key (AI screening)
- X.AI API key (AI analysis)
- DeepSeek API key (AI analysis)
- Unusual Whales API key (options flow)
- Angel One SmartAPI credentials
- Binance API credentials
- OANDA API credentials
- Alpaca API credentials

---

## Local Development Setup

### 1. Clone Repository
```bash
git clone https://github.com/signalix/signalixai-backend.git
cd signalixai-backend
```

### 2. Create Environment File
```bash
cp deployment/.env.production.template .env.local
# Edit .env.local with your local configuration
```

### 3. Start Services with Docker Compose
```bash
cd deployment
docker-compose -f docker-compose.production.yml up -d
```

### 4. Run Database Migrations
```bash
docker exec -it algo-builder alembic upgrade head
```

### 5. Verify Services
```bash
# Check all services are running
docker-compose ps

# Test health endpoints
curl http://localhost:8000/health  # Algo Builder
curl http://localhost:8001/health  # Backtesting
curl http://localhost:8002/health  # Screening
curl http://localhost:8003/health  # Alerts
```

---

## Staging Deployment

### 1. Build Docker Images
```bash
# Build all service images
docker build -f deployment/Dockerfile.algo-builder -t signalix/algo-builder:staging .
docker build -f deployment/Dockerfile.backtesting -t signalix/backtesting:staging .
docker build -f deployment/Dockerfile.screening -t signalix/screening:staging .
docker build -f deployment/Dockerfile.alerts -t signalix/alerts:staging .
```

### 2. Push to ECR
```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

# Tag and push images
docker tag signalix/algo-builder:staging ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/algo-builder:staging
docker push ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/algo-builder:staging

docker tag signalix/backtesting:staging ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/backtesting:staging
docker push ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/backtesting:staging

docker tag signalix/screening:staging ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/screening:staging
docker push ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/screening:staging

docker tag signalix/alerts:staging ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/alerts:staging
docker push ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/alerts:staging
```

### 3. Deploy Infrastructure with CDK
```bash
cd deployment
npm install  # Install CDK dependencies

# Bootstrap CDK (first time only)
cdk bootstrap aws://ACCOUNT_ID/us-east-1

# Deploy to staging
cdk deploy SignalixAlgoBackendStack-Staging \
  --context environment=staging \
  --require-approval never
```

### 4. Configure Secrets Manager
```bash
# Update API keys in Secrets Manager
aws secretsmanager update-secret \
  --secret-id signalix/algo-backend/api-keys \
  --secret-string file://secrets.json
```

### 5. Run Database Migrations
```bash
# Connect to ECS task
aws ecs execute-command \
  --cluster signalix-algo-backend-staging \
  --task TASK_ID \
  --container algo-builder \
  --interactive \
  --command "/bin/bash"

# Inside container
alembic upgrade head
```

### 6. Run Integration Tests
```bash
# Set staging API endpoint
export API_BASE_URL=https://staging-api.signalix.com

# Run test suite
pytest tests/integration/ -v --tb=short
```

---

## Production Deployment

### Pre-Deployment Checklist

- [ ] All staging tests passed
- [ ] Database backup completed
- [ ] API keys configured in Secrets Manager
- [ ] SSL certificates valid and renewed
- [ ] Monitoring and alerting configured
- [ ] Rollback plan documented
- [ ] Team notified of deployment window
- [ ] Maintenance page ready (if needed)

### 1. Build Production Images
```bash
# Build with production tag
docker build -f deployment/Dockerfile.algo-builder -t signalix/algo-builder:v1.0.0 .
docker build -f deployment/Dockerfile.backtesting -t signalix/backtesting:v1.0.0 .
docker build -f deployment/Dockerfile.screening -t signalix/screening:v1.0.0 .
docker build -f deployment/Dockerfile.alerts -t signalix/alerts:v1.0.0 .
```

### 2. Push to ECR
```bash
# Tag and push with version
docker tag signalix/algo-builder:v1.0.0 ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/algo-builder:v1.0.0
docker push ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/algo-builder:v1.0.0

# Repeat for other services...
```

### 3. Deploy Infrastructure
```bash
# Deploy to production
cdk deploy SignalixAlgoBackendStack-Production \
  --context environment=production \
  --require-approval never
```

### 4. Database Migration
```bash
# Create database backup first
aws rds create-db-cluster-snapshot \
  --db-cluster-identifier signalix-prod \
  --db-cluster-snapshot-identifier signalix-prod-pre-deploy-$(date +%Y%m%d)

# Run migrations
aws ecs execute-command \
  --cluster signalix-algo-backend-production \
  --task TASK_ID \
  --container algo-builder \
  --interactive \
  --command "alembic upgrade head"
```

### 5. Update DNS
```bash
# Update Route53 records to point to new ALB
aws route53 change-resource-record-sets \
  --hosted-zone-id ZONE_ID \
  --change-batch file://dns-update.json
```

### 6. Smoke Tests
```bash
# Test all service endpoints
curl https://api.signalix.com/api/v1/algo/templates
curl https://api.signalix.com/api/v1/backtest/health
curl https://api.signalix.com/api/v1/screen/templates
curl https://api.signalix.com/api/v1/alerts/rules
```

### 7. Monitor Deployment
```bash
# Watch CloudWatch logs
aws logs tail /ecs/algo-builder --follow
aws logs tail /ecs/backtesting --follow
aws logs tail /ecs/screening --follow
aws logs tail /ecs/alerts --follow

# Monitor ECS service health
aws ecs describe-services \
  --cluster signalix-algo-backend-production \
  --services algo-builder backtesting screening alerts
```

---

## Rollback Procedure

### If Issues Detected

1. **Immediate Rollback**
```bash
# Revert to previous task definition
aws ecs update-service \
  --cluster signalix-algo-backend-production \
  --service algo-builder \
  --task-definition algo-builder:PREVIOUS_VERSION \
  --force-new-deployment
```

2. **Database Rollback** (if needed)
```bash
# Restore from snapshot
aws rds restore-db-cluster-from-snapshot \
  --db-cluster-identifier signalix-prod-rollback \
  --snapshot-identifier signalix-prod-pre-deploy-YYYYMMDD
```

3. **DNS Rollback**
```bash
# Point back to old infrastructure
aws route53 change-resource-record-sets \
  --hosted-zone-id ZONE_ID \
  --change-batch file://dns-rollback.json
```

---

## Post-Deployment

### 1. Verify All Services
- [ ] All health checks passing
- [ ] API endpoints responding
- [ ] WebSocket connections working
- [ ] Celery workers processing tasks
- [ ] Database connections stable
- [ ] Redis cache operational

### 2. Monitor Metrics
- [ ] CPU utilization < 70%
- [ ] Memory utilization < 80%
- [ ] API response times < 200ms (p95)
- [ ] Error rate < 0.1%
- [ ] Queue depths normal

### 3. Enable Auto-Scaling
```bash
# Verify auto-scaling policies
aws application-autoscaling describe-scaling-policies \
  --service-namespace ecs \
  --resource-id service/signalix-algo-backend-production/algo-builder
```

### 4. Update Documentation
- [ ] Update API documentation
- [ ] Update runbooks
- [ ] Document any issues encountered
- [ ] Update deployment notes

---

## Maintenance

### Regular Tasks

**Daily:**
- Monitor CloudWatch dashboards
- Check error logs
- Verify backup completion

**Weekly:**
- Review performance metrics
- Check auto-scaling events
- Update dependencies

**Monthly:**
- Security patches
- Certificate renewal check
- Cost optimization review

### Database Maintenance
```bash
# Vacuum and analyze
psql $DATABASE_URL -c "VACUUM ANALYZE;"

# Check TimescaleDB compression
psql $DATABASE_URL -c "SELECT * FROM timescaledb_information.compression_settings;"

# Refresh materialized views
psql $DATABASE_URL -c "REFRESH MATERIALIZED VIEW CONCURRENTLY screening_snapshot;"
```

### Redis Maintenance
```bash
# Check memory usage
redis-cli INFO memory

# Check keyspace
redis-cli INFO keyspace

# Flush expired keys
redis-cli --scan --pattern "compiled_strategy:*" | xargs redis-cli DEL
```

---

## Troubleshooting

### Service Won't Start
```bash
# Check logs
aws logs tail /ecs/SERVICE_NAME --follow

# Check task definition
aws ecs describe-task-definition --task-definition SERVICE_NAME

# Check security groups
aws ec2 describe-security-groups --group-ids SG_ID
```

### Database Connection Issues
```bash
# Test connection from ECS task
aws ecs execute-command \
  --cluster CLUSTER_NAME \
  --task TASK_ID \
  --container CONTAINER_NAME \
  --interactive \
  --command "psql $DATABASE_URL -c 'SELECT 1;'"
```

### High Memory Usage
```bash
# Check container metrics
aws ecs describe-tasks \
  --cluster CLUSTER_NAME \
  --tasks TASK_ARN

# Increase memory limit in task definition
# Redeploy service
```

### Queue Backlog
```bash
# Check queue depth
aws sqs get-queue-attributes \
  --queue-url QUEUE_URL \
  --attribute-names ApproximateNumberOfMessages

# Scale up workers
aws ecs update-service \
  --cluster CLUSTER_NAME \
  --service SERVICE_NAME \
  --desired-count 10
```

---

## Security

### Best Practices
1. **Secrets Management**
   - Never commit secrets to git
   - Use AWS Secrets Manager for all API keys
   - Rotate secrets regularly

2. **Network Security**
   - Use VPC with private subnets
   - Enable VPC Flow Logs
   - Restrict security group rules

3. **Access Control**
   - Use IAM roles for ECS tasks
   - Enable MFA for AWS console
   - Follow principle of least privilege

4. **Monitoring**
   - Enable CloudTrail
   - Set up CloudWatch alarms
   - Use AWS GuardDuty

### Security Checklist
- [ ] All secrets in Secrets Manager
- [ ] SSL/TLS enabled on all endpoints
- [ ] Security groups properly configured
- [ ] IAM roles follow least privilege
- [ ] CloudTrail enabled
- [ ] GuardDuty enabled
- [ ] VPC Flow Logs enabled
- [ ] Database encryption at rest
- [ ] Redis encryption in transit

---

## Support

### Contact
- **Email:** devops@signalix.com
- **Slack:** #algo-backend-ops
- **On-Call:** PagerDuty rotation

### Resources
- [API Documentation](https://docs.signalix.com/api)
- [Architecture Diagram](https://docs.signalix.com/architecture)
- [Runbooks](https://docs.signalix.com/runbooks)
- [Incident Response](https://docs.signalix.com/incident-response)

---

**Last Updated:** 2025-01-15  
**Version:** 1.0.0  
**Maintained By:** DevOps Team
