import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecs_patterns from 'aws-cdk-lib/aws-ecs-patterns';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as elasticache from 'aws-cdk-lib/aws-elasticache';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';

export class SignalixAlgoBackendStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // VPC
    const vpc = new ec2.Vpc(this, 'SignalixVPC', {
      maxAzs: 3,
      natGateways: 2,
      subnetConfiguration: [
        {
          cidrMask: 24,
          name: 'Public',
          subnetType: ec2.SubnetType.PUBLIC,
        },
        {
          cidrMask: 24,
          name: 'Private',
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
        },
        {
          cidrMask: 28,
          name: 'Isolated',
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
        },
      ],
    });

    // Security Groups
    const albSecurityGroup = new ec2.SecurityGroup(this, 'ALBSecurityGroup', {
      vpc,
      description: 'Security group for Application Load Balancer',
      allowAllOutbound: true,
    });
    albSecurityGroup.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(443), 'Allow HTTPS');
    albSecurityGroup.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(80), 'Allow HTTP');

    const ecsSecurityGroup = new ec2.SecurityGroup(this, 'ECSSecurityGroup', {
      vpc,
      description: 'Security group for ECS tasks',
      allowAllOutbound: true,
    });
    ecsSecurityGroup.addIngressRule(albSecurityGroup, ec2.Port.allTcp(), 'Allow from ALB');

    const dbSecurityGroup = new ec2.SecurityGroup(this, 'DBSecurityGroup', {
      vpc,
      description: 'Security group for RDS database',
      allowAllOutbound: false,
    });
    dbSecurityGroup.addIngressRule(ecsSecurityGroup, ec2.Port.tcp(5432), 'Allow from ECS');

    const redisSecurityGroup = new ec2.SecurityGroup(this, 'RedisSecurityGroup', {
      vpc,
      description: 'Security group for ElastiCache Redis',
      allowAllOutbound: false,
    });
    redisSecurityGroup.addIngressRule(ecsSecurityGroup, ec2.Port.tcp(6379), 'Allow from ECS');

    // Secrets Manager for API keys
    const apiKeysSecret = new secretsmanager.Secret(this, 'APIKeysSecret', {
      secretName: 'signalix/algo-backend/api-keys',
      description: 'API keys for external services',
      generateSecretString: {
        secretStringTemplate: JSON.stringify({
          GLASSNODE_API_KEY: '',
          POLYGON_API_KEY: '',
          XAI_API_KEY: '',
          DEEPSEEK_API_KEY: '',
          GOOGLE_API_KEY: '',
          UNUSUAL_WHALES_API_KEY: '',
        }),
        generateStringKey: 'JWT_SECRET',
      },
    });

    // RDS TimescaleDB (PostgreSQL with TimescaleDB extension)
    const dbCluster = new rds.DatabaseCluster(this, 'SignalixDB', {
      engine: rds.DatabaseClusterEngine.auroraPostgres({
        version: rds.AuroraPostgresEngineVersion.VER_15_3,
      }),
      credentials: rds.Credentials.fromGeneratedSecret('postgres'),
      instanceProps: {
        vpc,
        vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
        securityGroups: [dbSecurityGroup],
        instanceType: ec2.InstanceType.of(ec2.InstanceClass.R6G, ec2.InstanceSize.XLARGE),
      },
      instances: 2,
      backup: {
        retention: cdk.Duration.days(7),
        preferredWindow: '03:00-04:00',
      },
      storageEncrypted: true,
      deletionProtection: true,
    });

    // ElastiCache Redis
    const redisSubnetGroup = new elasticache.CfnSubnetGroup(this, 'RedisSubnetGroup', {
      description: 'Subnet group for Redis cluster',
      subnetIds: vpc.selectSubnets({ subnetType: ec2.SubnetType.PRIVATE_ISOLATED }).subnetIds,
    });

    const redisCluster = new elasticache.CfnReplicationGroup(this, 'RedisCluster', {
      replicationGroupDescription: 'Redis cluster for Signalix',
      engine: 'redis',
      cacheNodeType: 'cache.r6g.large',
      numCacheClusters: 2,
      automaticFailoverEnabled: true,
      multiAzEnabled: true,
      cacheSubnetGroupName: redisSubnetGroup.ref,
      securityGroupIds: [redisSecurityGroup.securityGroupId],
      atRestEncryptionEnabled: true,
      transitEncryptionEnabled: true,
      snapshotRetentionLimit: 5,
      snapshotWindow: '03:00-05:00',
    });

    // SQS Queues
    const backtestQueue = new sqs.Queue(this, 'BacktestQueue', {
      queueName: 'backtest-queue',
      visibilityTimeout: cdk.Duration.minutes(15),
      retentionPeriod: cdk.Duration.days(4),
      deadLetterQueue: {
        queue: new sqs.Queue(this, 'BacktestDLQ', {
          queueName: 'backtest-dlq',
          retentionPeriod: cdk.Duration.days(14),
        }),
        maxReceiveCount: 3,
      },
    });

    const alertQueue = new sqs.Queue(this, 'AlertQueue', {
      queueName: 'alert-queue.fifo',
      fifo: true,
      contentBasedDeduplication: true,
      visibilityTimeout: cdk.Duration.seconds(30),
      retentionPeriod: cdk.Duration.days(4),
      deadLetterQueue: {
        queue: new sqs.Queue(this, 'AlertDLQ', {
          queueName: 'alert-dlq.fifo',
          fifo: true,
          retentionPeriod: cdk.Duration.days(14),
        }),
        maxReceiveCount: 3,
      },
    });

    const screeningQueue = new sqs.Queue(this, 'ScreeningQueue', {
      queueName: 'screening-queue',
      visibilityTimeout: cdk.Duration.minutes(5),
      retentionPeriod: cdk.Duration.days(4),
      deadLetterQueue: {
        queue: new sqs.Queue(this, 'ScreeningDLQ', {
          queueName: 'screening-dlq',
          retentionPeriod: cdk.Duration.days(14),
        }),
        maxReceiveCount: 3,
      },
    });

    // ECS Cluster
    const cluster = new ecs.Cluster(this, 'SignalixCluster', {
      vpc,
      clusterName: 'signalix-algo-backend',
      containerInsights: true,
    });

    // CloudWatch Log Groups
    const algoBuilderLogGroup = new logs.LogGroup(this, 'AlgoBuilderLogs', {
      logGroupName: '/ecs/algo-builder',
      retention: logs.RetentionDays.ONE_MONTH,
    });

    const backtestingLogGroup = new logs.LogGroup(this, 'BacktestingLogs', {
      logGroupName: '/ecs/backtesting',
      retention: logs.RetentionDays.ONE_MONTH,
    });

    const screeningLogGroup = new logs.LogGroup(this, 'ScreeningLogs', {
      logGroupName: '/ecs/screening',
      retention: logs.RetentionDays.ONE_MONTH,
    });

    const alertsLogGroup = new logs.LogGroup(this, 'AlertsLogs', {
      logGroupName: '/ecs/alerts',
      retention: logs.RetentionDays.ONE_MONTH,
    });

    // Task Execution Role
    const taskExecutionRole = new iam.Role(this, 'TaskExecutionRole', {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AmazonECSTaskExecutionRolePolicy'),
      ],
    });

    apiKeysSecret.grantRead(taskExecutionRole);

    // Task Role (for application permissions)
    const taskRole = new iam.Role(this, 'TaskRole', {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
    });

    backtestQueue.grantSendMessages(taskRole);
    alertQueue.grantSendMessages(taskRole);
    screeningQueue.grantSendMessages(taskRole);

    // Environment variables common to all services
    const commonEnvironment = {
      ENVIRONMENT: 'production',
      DATABASE_URL: `postgresql://postgres:${dbCluster.secret?.secretValueFromJson('password')}@${dbCluster.clusterEndpoint.hostname}:5432/signalix`,
      REDIS_URL: `redis://${redisCluster.attrPrimaryEndPointAddress}:${redisCluster.attrPrimaryEndPointPort}`,
      CELERY_BROKER_URL: `redis://${redisCluster.attrPrimaryEndPointAddress}:${redisCluster.attrPrimaryEndPointPort}/0`,
    };

    // 1. Algo Builder Service
    const algoBuilderService = new ecs_patterns.ApplicationLoadBalancedFargateService(this, 'AlgoBuilderService', {
      cluster,
      serviceName: 'algo-builder',
      cpu: 2048,
      memoryLimitMiB: 4096,
      desiredCount: 2,
      taskImageOptions: {
        image: ecs.ContainerImage.fromAsset('../', {
          file: 'deployment/Dockerfile.algo-builder',
        }),
        containerPort: 8000,
        environment: {
          ...commonEnvironment,
          SERVICE_NAME: 'algo-builder',
        },
        secrets: {
          JWT_SECRET: ecs.Secret.fromSecretsManager(apiKeysSecret, 'JWT_SECRET'),
        },
        logDriver: ecs.LogDrivers.awsLogs({
          streamPrefix: 'algo-builder',
          logGroup: algoBuilderLogGroup,
        }),
        executionRole: taskExecutionRole,
        taskRole: taskRole,
      },
      publicLoadBalancer: true,
      securityGroups: [ecsSecurityGroup],
    });

    // Auto-scaling for Algo Builder
    const algoBuilderScaling = algoBuilderService.service.autoScaleTaskCount({
      minCapacity: 2,
      maxCapacity: 10,
    });
    algoBuilderScaling.scaleOnCpuUtilization('AlgoBuilderCpuScaling', {
      targetUtilizationPercent: 70,
      scaleInCooldown: cdk.Duration.seconds(60),
      scaleOutCooldown: cdk.Duration.seconds(60),
    });

    // 2. Backtesting Service
    const backtestingService = new ecs_patterns.ApplicationLoadBalancedFargateService(this, 'BacktestingService', {
      cluster,
      serviceName: 'backtesting',
      cpu: 4096,
      memoryLimitMiB: 8192,
      desiredCount: 2,
      taskImageOptions: {
        image: ecs.ContainerImage.fromAsset('../', {
          file: 'deployment/Dockerfile.backtesting',
        }),
        containerPort: 8001,
        environment: {
          ...commonEnvironment,
          SERVICE_NAME: 'backtesting',
          SQS_BACKTEST_QUEUE_URL: backtestQueue.queueUrl,
        },
        secrets: {
          POLYGON_API_KEY: ecs.Secret.fromSecretsManager(apiKeysSecret, 'POLYGON_API_KEY'),
        },
        logDriver: ecs.LogDrivers.awsLogs({
          streamPrefix: 'backtesting',
          logGroup: backtestingLogGroup,
        }),
        executionRole: taskExecutionRole,
        taskRole: taskRole,
      },
      publicLoadBalancer: true,
      securityGroups: [ecsSecurityGroup],
    });

    // Auto-scaling for Backtesting (based on SQS queue depth)
    const backtestingScaling = backtestingService.service.autoScaleTaskCount({
      minCapacity: 2,
      maxCapacity: 20,
    });
    backtestingScaling.scaleOnMetric('BacktestingQueueScaling', {
      metric: backtestQueue.metricApproximateNumberOfMessagesVisible(),
      scalingSteps: [
        { upper: 0, change: -1 },
        { lower: 5, change: +1 },
        { lower: 10, change: +2 },
        { lower: 20, change: +3 },
      ],
      adjustmentType: ecs.AdjustmentType.CHANGE_IN_CAPACITY,
    });

    // 3. Screening Service
    const screeningService = new ecs_patterns.ApplicationLoadBalancedFargateService(this, 'ScreeningService', {
      cluster,
      serviceName: 'screening',
      cpu: 2048,
      memoryLimitMiB: 4096,
      desiredCount: 2,
      taskImageOptions: {
        image: ecs.ContainerImage.fromAsset('../', {
          file: 'deployment/Dockerfile.screening',
        }),
        containerPort: 8002,
        environment: {
          ...commonEnvironment,
          SERVICE_NAME: 'screening',
          SQS_SCREENING_QUEUE_URL: screeningQueue.queueUrl,
        },
        secrets: {
          GOOGLE_API_KEY: ecs.Secret.fromSecretsManager(apiKeysSecret, 'GOOGLE_API_KEY'),
          XAI_API_KEY: ecs.Secret.fromSecretsManager(apiKeysSecret, 'XAI_API_KEY'),
          DEEPSEEK_API_KEY: ecs.Secret.fromSecretsManager(apiKeysSecret, 'DEEPSEEK_API_KEY'),
        },
        logDriver: ecs.LogDrivers.awsLogs({
          streamPrefix: 'screening',
          logGroup: screeningLogGroup,
        }),
        executionRole: taskExecutionRole,
        taskRole: taskRole,
      },
      publicLoadBalancer: true,
      securityGroups: [ecsSecurityGroup],
    });

    // Auto-scaling for Screening
    const screeningScaling = screeningService.service.autoScaleTaskCount({
      minCapacity: 2,
      maxCapacity: 10,
    });
    screeningScaling.scaleOnCpuUtilization('ScreeningCpuScaling', {
      targetUtilizationPercent: 70,
      scaleInCooldown: cdk.Duration.seconds(60),
      scaleOutCooldown: cdk.Duration.seconds(60),
    });

    // 4. Alerts Service
    const alertsService = new ecs_patterns.ApplicationLoadBalancedFargateService(this, 'AlertsService', {
      cluster,
      serviceName: 'alerts',
      cpu: 2048,
      memoryLimitMiB: 4096,
      desiredCount: 2,
      taskImageOptions: {
        image: ecs.ContainerImage.fromAsset('../', {
          file: 'deployment/Dockerfile.alerts',
        }),
        containerPort: 8003,
        environment: {
          ...commonEnvironment,
          SERVICE_NAME: 'alerts',
          SQS_ALERT_QUEUE_URL: alertQueue.queueUrl,
        },
        secrets: {
          GLASSNODE_API_KEY: ecs.Secret.fromSecretsManager(apiKeysSecret, 'GLASSNODE_API_KEY'),
          UNUSUAL_WHALES_API_KEY: ecs.Secret.fromSecretsManager(apiKeysSecret, 'UNUSUAL_WHALES_API_KEY'),
          XAI_API_KEY: ecs.Secret.fromSecretsManager(apiKeysSecret, 'XAI_API_KEY'),
        },
        logDriver: ecs.LogDrivers.awsLogs({
          streamPrefix: 'alerts',
          logGroup: alertsLogGroup,
        }),
        executionRole: taskExecutionRole,
        taskRole: taskRole,
      },
      publicLoadBalancer: true,
      securityGroups: [ecsSecurityGroup],
    });

    // Auto-scaling for Alerts
    const alertsScaling = alertsService.service.autoScaleTaskCount({
      minCapacity: 2,
      maxCapacity: 10,
    });
    alertsScaling.scaleOnCpuUtilization('AlertsCpuScaling', {
      targetUtilizationPercent: 70,
      scaleInCooldown: cdk.Duration.seconds(60),
      scaleOutCooldown: cdk.Duration.seconds(60),
    });

    // Outputs
    new cdk.CfnOutput(this, 'AlgoBuilderURL', {
      value: algoBuilderService.loadBalancer.loadBalancerDnsName,
      description: 'Algo Builder Service URL',
    });

    new cdk.CfnOutput(this, 'BacktestingURL', {
      value: backtestingService.loadBalancer.loadBalancerDnsName,
      description: 'Backtesting Service URL',
    });

    new cdk.CfnOutput(this, 'ScreeningURL', {
      value: screeningService.loadBalancer.loadBalancerDnsName,
      description: 'Screening Service URL',
    });

    new cdk.CfnOutput(this, 'AlertsURL', {
      value: alertsService.loadBalancer.loadBalancerDnsName,
      description: 'Alerts Service URL',
    });

    new cdk.CfnOutput(this, 'DatabaseEndpoint', {
      value: dbCluster.clusterEndpoint.hostname,
      description: 'RDS Database Endpoint',
    });

    new cdk.CfnOutput(this, 'RedisEndpoint', {
      value: redisCluster.attrPrimaryEndPointAddress,
      description: 'Redis Cluster Endpoint',
    });
  }
}
