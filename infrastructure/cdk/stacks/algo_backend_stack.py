"""
AWS CDK Stack for Algo Builder, Backtesting, Screening & Alert Services
Creates ECS Fargate services, SQS queues, auto-scaling, and load balancing
"""

from aws_cdk import (
    Stack,
    Duration,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_sqs as sqs,
    aws_elasticloadbalancingv2 as elbv2,
    aws_logs as logs,
    aws_iam as iam,
    aws_secretsmanager as secretsmanager,
    aws_applicationautoscaling as appscaling,
    CfnOutput,
)
from constructs import Construct


class AlgoBackendStack(Stack):
    """
    Main infrastructure stack for algo backend services
    """

    def __init__(self, scope: Construct, construct_id: str, env_name: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name

        # Create VPC or use existing
        self.vpc = self._create_or_get_vpc()

        # Create ECS Cluster
        self.cluster = self._create_ecs_cluster()

        # Create SQS Queues
        self.queues = self._create_sqs_queues()

        # Create Secrets Manager for API keys
        self.secrets = self._create_secrets()

        # Create ECS Services
        self.algo_builder_service = self._create_algo_builder_service()
        self.backtest_service = self._create_backtest_service()
        self.screening_service = self._create_screening_service()
        self.alert_service = self._create_alert_service()

        # Create outputs
        self._create_outputs()

    def _create_or_get_vpc(self) -> ec2.Vpc:
        """
        Create a new VPC or use existing one
        """
        # For production, you might want to import an existing VPC
        # vpc = ec2.Vpc.from_lookup(self, "VPC", vpc_id="vpc-xxxxx")
        
        vpc = ec2.Vpc(
            self,
            "SignalixAIVPC",
            max_azs=2,  # Use 2 availability zones for high availability
            nat_gateways=1,  # Cost optimization: use 1 NAT gateway
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
        )
        return vpc

    def _create_ecs_cluster(self) -> ecs.Cluster:
        """
        Create ECS Cluster for running Fargate services
        """
        cluster = ecs.Cluster(
            self,
            "AlgoBackendCluster",
            vpc=self.vpc,
            cluster_name=f"signalixai-algo-backend-{self.env_name}",
            container_insights=True,  # Enable CloudWatch Container Insights
        )
        return cluster

    def _create_sqs_queues(self) -> dict:
        """
        Create SQS queues for async task processing
        """
        # Backtest Queue (Standard)
        backtest_queue = sqs.Queue(
            self,
            "BacktestQueue",
            queue_name=f"backtest-queue-{self.env_name}",
            visibility_timeout=Duration.minutes(30),  # Long-running backtests
            retention_period=Duration.days(14),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=sqs.Queue(
                    self,
                    "BacktestDLQ",
                    queue_name=f"backtest-dlq-{self.env_name}",
                ),
            ),
        )

        # Alert Queue (FIFO for ordered delivery)
        alert_queue = sqs.Queue(
            self,
            "AlertQueue",
            queue_name=f"alert-queue-{self.env_name}.fifo",
            fifo=True,
            content_based_deduplication=True,
            visibility_timeout=Duration.seconds(30),
            retention_period=Duration.days(4),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=sqs.Queue(
                    self,
                    "AlertDLQ",
                    queue_name=f"alert-dlq-{self.env_name}.fifo",
                    fifo=True,
                ),
            ),
        )

        # Screening Queue (Standard)
        screening_queue = sqs.Queue(
            self,
            "ScreeningQueue",
            queue_name=f"screening-queue-{self.env_name}",
            visibility_timeout=Duration.minutes(5),
            retention_period=Duration.days(7),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=sqs.Queue(
                    self,
                    "ScreeningDLQ",
                    queue_name=f"screening-dlq-{self.env_name}",
                ),
            ),
        )

        return {
            "backtest": backtest_queue,
            "alert": alert_queue,
            "screening": screening_queue,
        }

    def _create_secrets(self) -> dict:
        """
        Create AWS Secrets Manager secrets for API keys
        """
        # Create a secret for all API keys
        api_keys_secret = secretsmanager.Secret(
            self,
            "ApiKeysSecret",
            secret_name=f"signalixai/algo-backend/{self.env_name}/api-keys",
            description="API keys for external services",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{}',
                generate_string_key="placeholder",
            ),
        )

        return {
            "api_keys": api_keys_secret,
        }

    def _create_task_role(self, service_name: str) -> iam.Role:
        """
        Create IAM role for ECS task with necessary permissions
        """
        role = iam.Role(
            self,
            f"{service_name}TaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description=f"Task role for {service_name}",
        )

        # Grant access to Secrets Manager
        self.secrets["api_keys"].grant_read(role)

        # Grant access to SQS queues
        for queue in self.queues.values():
            queue.grant_send_messages(role)
            queue.grant_consume_messages(role)

        # Grant CloudWatch Logs permissions
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                resources=["*"],
            )
        )

        return role

    def _create_algo_builder_service(self) -> ecs_patterns.ApplicationLoadBalancedFargateService:
        """
        Create Algo Builder ECS Fargate service with ALB
        """
        task_role = self._create_task_role("AlgoBuilder")

        service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "AlgoBuilderService",
            cluster=self.cluster,
            service_name=f"algo-builder-{self.env_name}",
            cpu=512,  # 0.5 vCPU
            memory_limit_mib=1024,  # 1 GB
            desired_count=2,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset(
                    "../../",
                    file="services/algo_builder/Dockerfile",
                ),
                container_port=8010,
                task_role=task_role,
                environment={
                    "SERVICE_NAME": "algo-builder",
                    "ENVIRONMENT": self.env_name,
                    "BACKTEST_QUEUE_URL": self.queues["backtest"].queue_url,
                },
                secrets={
                    "GLASSNODE_API_KEY": ecs.Secret.from_secrets_manager(
                        self.secrets["api_keys"], "GLASSNODE_API_KEY"
                    ),
                    "POLYGON_API_KEY": ecs.Secret.from_secrets_manager(
                        self.secrets["api_keys"], "POLYGON_API_KEY"
                    ),
                    "XAI_API_KEY": ecs.Secret.from_secrets_manager(
                        self.secrets["api_keys"], "XAI_API_KEY"
                    ),
                    "DEEPSEEK_API_KEY": ecs.Secret.from_secrets_manager(
                        self.secrets["api_keys"], "DEEPSEEK_API_KEY"
                    ),
                    "GOOGLE_API_KEY": ecs.Secret.from_secrets_manager(
                        self.secrets["api_keys"], "GOOGLE_API_KEY"
                    ),
                    "UNUSUAL_WHALES_API_KEY": ecs.Secret.from_secrets_manager(
                        self.secrets["api_keys"], "UNUSUAL_WHALES_API_KEY"
                    ),
                },
                log_driver=ecs.LogDrivers.aws_logs(
                    stream_prefix="algo-builder",
                    log_retention=logs.RetentionDays.ONE_WEEK,
                ),
            ),
            public_load_balancer=True,
        )

        # Configure auto-scaling
        scaling = service.service.auto_scale_task_count(
            min_capacity=2,
            max_capacity=10,
        )

        scaling.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=70,
            scale_in_cooldown=Duration.seconds(60),
            scale_out_cooldown=Duration.seconds(60),
        )

        scaling.scale_on_memory_utilization(
            "MemoryScaling",
            target_utilization_percent=80,
            scale_in_cooldown=Duration.seconds(60),
            scale_out_cooldown=Duration.seconds(60),
        )

        # Configure health check
        service.target_group.configure_health_check(
            path="/health",
            interval=Duration.seconds(30),
            timeout=Duration.seconds(10),
            healthy_threshold_count=2,
            unhealthy_threshold_count=3,
        )

        return service

    def _create_backtest_service(self) -> ecs_patterns.ApplicationLoadBalancedFargateService:
        """
        Create Backtesting ECS Fargate service with ALB
        """
        task_role = self._create_task_role("Backtest")

        service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "BacktestService",
            cluster=self.cluster,
            service_name=f"backtest-{self.env_name}",
            cpu=2048,  # 2 vCPU (compute-intensive)
            memory_limit_mib=4096,  # 4 GB
            desired_count=2,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset(
                    "../../",
                    file="services/backtesting/Dockerfile",
                ),
                container_port=8011,
                task_role=task_role,
                environment={
                    "SERVICE_NAME": "backtest",
                    "ENVIRONMENT": self.env_name,
                    "BACKTEST_QUEUE_URL": self.queues["backtest"].queue_url,
                },
                secrets={
                    "GLASSNODE_API_KEY": ecs.Secret.from_secrets_manager(
                        self.secrets["api_keys"], "GLASSNODE_API_KEY"
                    ),
                    "POLYGON_API_KEY": ecs.Secret.from_secrets_manager(
                        self.secrets["api_keys"], "POLYGON_API_KEY"
                    ),
                    "XAI_API_KEY": ecs.Secret.from_secrets_manager(
                        self.secrets["api_keys"], "XAI_API_KEY"
                    ),
                    "DEEPSEEK_API_KEY": ecs.Secret.from_secrets_manager(
                        self.secrets["api_keys"], "DEEPSEEK_API_KEY"
                    ),
                    "GOOGLE_API_KEY": ecs.Secret.from_secrets_manager(
                        self.secrets["api_keys"], "GOOGLE_API_KEY"
                    ),
                    "UNUSUAL_WHALES_API_KEY": ecs.Secret.from_secrets_manager(
                        self.secrets["api_keys"], "UNUSUAL_WHALES_API_KEY"
                    ),
                },
                log_driver=ecs.LogDrivers.aws_logs(
                    stream_prefix="backtest",
                    log_retention=logs.RetentionDays.ONE_WEEK,
                ),
            ),
            public_load_balancer=True,
        )

        # Configure auto-scaling based on SQS queue depth
        scaling = service.service.auto_scale_task_count(
            min_capacity=2,
            max_capacity=20,
        )

        scaling.scale_on_metric(
            "QueueDepthScaling",
            metric=self.queues["backtest"].metric_approximate_number_of_messages_visible(),
            scaling_steps=[
                appscaling.ScalingInterval(upper=0, change=-1),
                appscaling.ScalingInterval(lower=5, change=+2),
                appscaling.ScalingInterval(lower=10, change=+5),
            ],
            adjustment_type=appscaling.AdjustmentType.CHANGE_IN_CAPACITY,
        )

        # Configure health check
        service.target_group.configure_health_check(
            path="/health",
            interval=Duration.seconds(30),
            timeout=Duration.seconds(10),
            healthy_threshold_count=2,
            unhealthy_threshold_count=3,
        )

        return service

    def _create_screening_service(self) -> ecs_patterns.ApplicationLoadBalancedFargateService:
        """
        Create Screening ECS Fargate service with ALB
        """
        task_role = self._create_task_role("Screening")

        service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "ScreeningService",
            cluster=self.cluster,
            service_name=f"screening-{self.env_name}",
            cpu=1024,  # 1 vCPU
            memory_limit_mib=2048,  # 2 GB
            desired_count=2,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset(
                    "../../",
                    file="services/screening/Dockerfile",
                ),
                container_port=8012,
                task_role=task_role,
                environment={
                    "SERVICE_NAME": "screening",
                    "ENVIRONMENT": self.env_name,
                    "SCREENING_QUEUE_URL": self.queues["screening"].queue_url,
                },
                secrets={
                    "GLASSNODE_API_KEY": ecs.Secret.from_secrets_manager(
                        self.secrets["api_keys"], "GLASSNODE_API_KEY"
                    ),
                    "POLYGON_API_KEY": ecs.Secret.from_secrets_manager(
                        self.secrets["api_keys"], "POLYGON_API_KEY"
                    ),
                    "XAI_API_KEY": ecs.Secret.from_secrets_manager(
                        self.secrets["api_keys"], "XAI_API_KEY"
                    ),
                    "DEEPSEEK_API_KEY": ecs.Secret.from_secrets_manager(
                        self.secrets["api_keys"], "DEEPSEEK_API_KEY"
                    ),
                    "GOOGLE_API_KEY": ecs.Secret.from_secrets_manager(
                        self.secrets["api_keys"], "GOOGLE_API_KEY"
                    ),
                    "UNUSUAL_WHALES_API_KEY": ecs.Secret.from_secrets_manager(
                        self.secrets["api_keys"], "UNUSUAL_WHALES_API_KEY"
                    ),
                },
                log_driver=ecs.LogDrivers.aws_logs(
                    stream_prefix="screening",
                    log_retention=logs.RetentionDays.ONE_WEEK,
                ),
            ),
            public_load_balancer=True,
        )

        # Configure auto-scaling
        scaling = service.service.auto_scale_task_count(
            min_capacity=2,
            max_capacity=10,
        )

        scaling.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=70,
            scale_in_cooldown=Duration.seconds(60),
            scale_out_cooldown=Duration.seconds(60),
        )

        # Configure health check
        service.target_group.configure_health_check(
            path="/health",
            interval=Duration.seconds(30),
            timeout=Duration.seconds(10),
            healthy_threshold_count=2,
            unhealthy_threshold_count=3,
        )

        return service

    def _create_alert_service(self) -> ecs_patterns.ApplicationLoadBalancedFargateService:
        """
        Create Alert ECS Fargate service with ALB
        """
        task_role = self._create_task_role("Alert")

        service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "AlertService",
            cluster=self.cluster,
            service_name=f"alert-{self.env_name}",
            cpu=1024,  # 1 vCPU
            memory_limit_mib=2048,  # 2 GB
            desired_count=2,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset(
                    "../../",
                    file="services/alerts/Dockerfile",
                ),
                container_port=8013,
                task_role=task_role,
                environment={
                    "SERVICE_NAME": "alert",
                    "ENVIRONMENT": self.env_name,
                    "ALERT_QUEUE_URL": self.queues["alert"].queue_url,
                },
                secrets={
                    "GLASSNODE_API_KEY": ecs.Secret.from_secrets_manager(
                        self.secrets["api_keys"], "GLASSNODE_API_KEY"
                    ),
                    "POLYGON_API_KEY": ecs.Secret.from_secrets_manager(
                        self.secrets["api_keys"], "POLYGON_API_KEY"
                    ),
                    "XAI_API_KEY": ecs.Secret.from_secrets_manager(
                        self.secrets["api_keys"], "XAI_API_KEY"
                    ),
                    "DEEPSEEK_API_KEY": ecs.Secret.from_secrets_manager(
                        self.secrets["api_keys"], "DEEPSEEK_API_KEY"
                    ),
                    "GOOGLE_API_KEY": ecs.Secret.from_secrets_manager(
                        self.secrets["api_keys"], "GOOGLE_API_KEY"
                    ),
                    "UNUSUAL_WHALES_API_KEY": ecs.Secret.from_secrets_manager(
                        self.secrets["api_keys"], "UNUSUAL_WHALES_API_KEY"
                    ),
                },
                log_driver=ecs.LogDrivers.aws_logs(
                    stream_prefix="alert",
                    log_retention=logs.RetentionDays.ONE_WEEK,
                ),
            ),
            public_load_balancer=True,
        )

        # Configure auto-scaling
        scaling = service.service.auto_scale_task_count(
            min_capacity=2,
            max_capacity=10,
        )

        scaling.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=70,
            scale_in_cooldown=Duration.seconds(60),
            scale_out_cooldown=Duration.seconds(60),
        )

        # Configure health check
        service.target_group.configure_health_check(
            path="/health",
            interval=Duration.seconds(30),
            timeout=Duration.seconds(10),
            healthy_threshold_count=2,
            unhealthy_threshold_count=3,
        )

        return service

    def _create_outputs(self):
        """
        Create CloudFormation outputs for service endpoints
        """
        CfnOutput(
            self,
            "AlgoBuilderServiceURL",
            value=self.algo_builder_service.load_balancer.load_balancer_dns_name,
            description="Algo Builder Service Load Balancer URL",
        )

        CfnOutput(
            self,
            "BacktestServiceURL",
            value=self.backtest_service.load_balancer.load_balancer_dns_name,
            description="Backtest Service Load Balancer URL",
        )

        CfnOutput(
            self,
            "ScreeningServiceURL",
            value=self.screening_service.load_balancer.load_balancer_dns_name,
            description="Screening Service Load Balancer URL",
        )

        CfnOutput(
            self,
            "AlertServiceURL",
            value=self.alert_service.load_balancer.load_balancer_dns_name,
            description="Alert Service Load Balancer URL",
        )

        CfnOutput(
            self,
            "BacktestQueueURL",
            value=self.queues["backtest"].queue_url,
            description="Backtest SQS Queue URL",
        )

        CfnOutput(
            self,
            "AlertQueueURL",
            value=self.queues["alert"].queue_url,
            description="Alert SQS FIFO Queue URL",
        )

        CfnOutput(
            self,
            "ScreeningQueueURL",
            value=self.queues["screening"].queue_url,
            description="Screening SQS Queue URL",
        )
