#!/bin/bash

# Deploy Celery Beat to AWS ECS Fargate
# This script deploys the Celery Beat scheduler as a separate ECS service

set -e

# Configuration
AWS_REGION="${AWS_REGION:-ap-south-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID}"
CLUSTER_NAME="${CLUSTER_NAME:-signalix-cluster}"
SERVICE_NAME="signalix-celery-beat"
TASK_FAMILY="signalix-celery-beat"
ECR_REPOSITORY="signalix-backend"
VPC_ID="${VPC_ID}"
SUBNET_IDS="${SUBNET_IDS}"  # Comma-separated list
SECURITY_GROUP_ID="${SECURITY_GROUP_ID}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================="
echo "Deploying Celery Beat to ECS Fargate"
echo "========================================="
echo ""

# Check required environment variables
if [ -z "$AWS_ACCOUNT_ID" ]; then
    echo -e "${RED}Error: AWS_ACCOUNT_ID is not set${NC}"
    exit 1
fi

if [ -z "$VPC_ID" ]; then
    echo -e "${RED}Error: VPC_ID is not set${NC}"
    exit 1
fi

if [ -z "$SUBNET_IDS" ]; then
    echo -e "${RED}Error: SUBNET_IDS is not set${NC}"
    exit 1
fi

if [ -z "$SECURITY_GROUP_ID" ]; then
    echo -e "${RED}Error: SECURITY_GROUP_ID is not set${NC}"
    exit 1
fi

# Step 1: Build and push Docker image
echo -e "${YELLOW}Step 1: Building and pushing Docker image...${NC}"

# Login to ECR
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Build image
docker build -t $ECR_REPOSITORY:latest .

# Tag image
docker tag $ECR_REPOSITORY:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:latest

# Push image
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:latest

echo -e "${GREEN}✓ Docker image built and pushed${NC}"
echo ""

# Step 2: Create CloudWatch log group
echo -e "${YELLOW}Step 2: Creating CloudWatch log group...${NC}"

aws logs create-log-group \
    --log-group-name /ecs/$SERVICE_NAME \
    --region $AWS_REGION \
    2>/dev/null || echo "Log group already exists"

echo -e "${GREEN}✓ CloudWatch log group ready${NC}"
echo ""

# Step 3: Update task definition
echo -e "${YELLOW}Step 3: Updating ECS task definition...${NC}"

# Replace placeholders in task definition
sed -e "s/ACCOUNT_ID/$AWS_ACCOUNT_ID/g" \
    -e "s/REGION/$AWS_REGION/g" \
    ecs-celery-beat-task-definition.json > /tmp/task-definition.json

# Register task definition
TASK_DEFINITION_ARN=$(aws ecs register-task-definition \
    --cli-input-json file:///tmp/task-definition.json \
    --region $AWS_REGION \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text)

echo -e "${GREEN}✓ Task definition registered: $TASK_DEFINITION_ARN${NC}"
echo ""

# Step 4: Create or update ECS service
echo -e "${YELLOW}Step 4: Creating/updating ECS service...${NC}"

# Check if service exists
SERVICE_EXISTS=$(aws ecs describe-services \
    --cluster $CLUSTER_NAME \
    --services $SERVICE_NAME \
    --region $AWS_REGION \
    --query 'services[0].status' \
    --output text 2>/dev/null || echo "MISSING")

if [ "$SERVICE_EXISTS" = "MISSING" ] || [ "$SERVICE_EXISTS" = "INACTIVE" ]; then
    # Create new service
    echo "Creating new service..."
    
    aws ecs create-service \
        --cluster $CLUSTER_NAME \
        --service-name $SERVICE_NAME \
        --task-definition $TASK_FAMILY \
        --desired-count 1 \
        --launch-type FARGATE \
        --platform-version LATEST \
        --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_IDS],securityGroups=[$SECURITY_GROUP_ID],assignPublicIp=ENABLED}" \
        --region $AWS_REGION \
        --enable-execute-command \
        --tags key=Name,value=$SERVICE_NAME key=Environment,value=production key=Service,value=celery-beat
    
    echo -e "${GREEN}✓ Service created${NC}"
else
    # Update existing service
    echo "Updating existing service..."
    
    aws ecs update-service \
        --cluster $CLUSTER_NAME \
        --service $SERVICE_NAME \
        --task-definition $TASK_FAMILY \
        --force-new-deployment \
        --region $AWS_REGION
    
    echo -e "${GREEN}✓ Service updated${NC}"
fi

echo ""

# Step 5: Wait for service to stabilize
echo -e "${YELLOW}Step 5: Waiting for service to stabilize...${NC}"

aws ecs wait services-stable \
    --cluster $CLUSTER_NAME \
    --services $SERVICE_NAME \
    --region $AWS_REGION

echo -e "${GREEN}✓ Service is stable${NC}"
echo ""

# Step 6: Verify deployment
echo -e "${YELLOW}Step 6: Verifying deployment...${NC}"

# Get service status
SERVICE_STATUS=$(aws ecs describe-services \
    --cluster $CLUSTER_NAME \
    --services $SERVICE_NAME \
    --region $AWS_REGION \
    --query 'services[0].[status,runningCount,desiredCount]' \
    --output text)

echo "Service Status: $SERVICE_STATUS"

# Get task ARN
TASK_ARN=$(aws ecs list-tasks \
    --cluster $CLUSTER_NAME \
    --service-name $SERVICE_NAME \
    --region $AWS_REGION \
    --query 'taskArns[0]' \
    --output text)

if [ "$TASK_ARN" != "None" ] && [ -n "$TASK_ARN" ]; then
    echo "Task ARN: $TASK_ARN"
    
    # Get task status
    TASK_STATUS=$(aws ecs describe-tasks \
        --cluster $CLUSTER_NAME \
        --tasks $TASK_ARN \
        --region $AWS_REGION \
        --query 'tasks[0].[lastStatus,healthStatus]' \
        --output text)
    
    echo "Task Status: $TASK_STATUS"
fi

echo -e "${GREEN}✓ Deployment verified${NC}"
echo ""

# Step 7: Display logs command
echo "========================================="
echo -e "${GREEN}Deployment Complete!${NC}"
echo "========================================="
echo ""
echo "To view logs:"
echo "  aws logs tail /ecs/$SERVICE_NAME --follow --region $AWS_REGION"
echo ""
echo "To check service status:"
echo "  aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME --region $AWS_REGION"
echo ""
echo "To scale service:"
echo "  aws ecs update-service --cluster $CLUSTER_NAME --service $SERVICE_NAME --desired-count N --region $AWS_REGION"
echo ""
echo "To stop service:"
echo "  aws ecs update-service --cluster $CLUSTER_NAME --service $SERVICE_NAME --desired-count 0 --region $AWS_REGION"
echo ""

# Cleanup
rm -f /tmp/task-definition.json
