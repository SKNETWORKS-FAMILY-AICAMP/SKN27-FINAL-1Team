from __future__ import annotations

import json
from pathlib import Path

from aws_cdk import (
    Aws,
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    TimeZone,
    aws_certificatemanager as acm,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_cognito as cognito,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_elasticloadbalancingv2 as elbv2,
    aws_iam as iam,
    aws_logs as logs,
    aws_rds as rds,
    aws_route53 as route53,
    aws_route53_targets as route53_targets,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_scheduler as scheduler,
    aws_scheduler_targets as scheduler_targets,
    aws_secretsmanager as secretsmanager,
    aws_sqs as sqs,
)
from constructs import Construct


REPO_ROOT = Path(__file__).resolve().parents[1]
MCP_SCOPE_NAMES = (
    "inventory.read",
    "recipe.read",
    "guide.read",
    "receipt.write",
    "shopping.write",
    "calendar.write",
)


class BobbeoriStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        environment_name = self.node.try_get_context("environment") or "dev"
        root_domain = self._required_context("root_domain")
        hosted_zone_id = self._required_context("hosted_zone_id")
        cognito_domain_prefix = self._required_context("cognito_domain_prefix")
        chatgpt_callbacks = self._context_list("chatgpt_callback_urls", required=True)
        codex_callbacks = self._context_list("codex_callback_urls", required=True)
        external_secret_name = (
            self.node.try_get_context("external_secret_name")
            or f"bobbeori/{environment_name}/external"
        )
        is_production = environment_name == "prod"

        api_host = f"api.{root_domain}"
        app_host = (
            str(self.node.try_get_context("frontend_host") or f"www.{root_domain}")
            .removeprefix("https://")
            .removeprefix("http://")
            .rstrip("/")
        )
        mcp_host = f"mcp.{root_domain}"
        mcp_url = f"https://{mcp_host}/mcp"

        vpc = ec2.Vpc(
            self,
            "Vpc",
            max_azs=2,
            nat_gateways=2 if is_production else 1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="application",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="database",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        receipts_bucket = s3.Bucket(
            self,
            "ReceiptsBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=is_production,
            removal_policy=RemovalPolicy.RETAIN if is_production else RemovalPolicy.DESTROY,
            auto_delete_objects=not is_production,
            lifecycle_rules=[
                s3.LifecycleRule(
                    abort_incomplete_multipart_upload_after=Duration.days(7),
                    noncurrent_version_expiration=Duration.days(90) if is_production else None,
                )
            ],
        )
        frontend_bucket = s3.Bucket(
            self,
            "FrontendBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN if is_production else RemovalPolicy.DESTROY,
            auto_delete_objects=not is_production,
        )

        app_security_group = ec2.SecurityGroup(
            self,
            "ApplicationSecurityGroup",
            vpc=vpc,
            allow_all_outbound=True,
            description="Bobbeori ECS tasks",
        )
        database_security_group = ec2.SecurityGroup(
            self,
            "DatabaseSecurityGroup",
            vpc=vpc,
            allow_all_outbound=False,
            description="Private PostgreSQL access",
        )
        database_security_group.add_ingress_rule(
            app_security_group,
            ec2.Port.tcp(5432),
            "PostgreSQL from Bobbeori tasks",
        )

        database = rds.DatabaseInstance(
            self,
            "Database",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_15
            ),
            credentials=rds.Credentials.from_generated_secret("bobbeori_user"),
            database_name="bobbeori_db",
            instance_type=ec2.InstanceType(
                "t4g.small" if is_production else "t4g.micro"
            ),
            allocated_storage=50,
            max_allocated_storage=200,
            storage_encrypted=True,
            multi_az=is_production,
            backup_retention=Duration.days(7 if is_production else 1),
            deletion_protection=is_production,
            publicly_accessible=False,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            security_groups=[database_security_group],
            removal_policy=RemovalPolicy.SNAPSHOT if is_production else RemovalPolicy.DESTROY,
        )
        if database.secret is None:
            raise RuntimeError("RDS credentials secret was not created")

        neo4j_host, neo4j_secret = self._create_neo4j(
            vpc=vpc,
            app_security_group=app_security_group,
            environment_name=environment_name,
            is_production=is_production,
        )

        user_pool, resource_server, oauth_scopes = self._create_cognito(
            environment_name=environment_name,
            cognito_domain_prefix=cognito_domain_prefix,
            chatgpt_callbacks=chatgpt_callbacks,
            codex_callbacks=codex_callbacks,
        )
        issuer_url = (
            f"https://cognito-idp.{Aws.REGION}.{Aws.URL_SUFFIX}/{user_pool.user_pool_id}"
        )

        application_secret = secretsmanager.Secret(
            self,
            "ApplicationSecret",
            secret_name=f"bobbeori/{environment_name}/application",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template="{}",
                generate_string_key="JWT_SECRET_KEY",
                password_length=64,
                exclude_punctuation=True,
            ),
        )
        external_secret = secretsmanager.Secret.from_secret_name_v2(
            self,
            "ExternalSecret",
            external_secret_name,
        )

        cluster = ecs.Cluster(
            self,
            "Cluster",
            vpc=vpc,
            container_insights_v2=ecs.ContainerInsights.ENABLED,
        )
        image = ecs.ContainerImage.from_asset(
            str(REPO_ROOT),
            file="app/backend/Dockerfile",
        )
        desired_count = 2 if is_production else 1

        common_environment = {
            "DEV_MODE": "false",
            "DB_HOST": database.db_instance_endpoint_address,
            "DB_PORT": database.db_instance_endpoint_port,
            "DB_NAME": "bobbeori_db",
            "NEO4J_URI": f"bolt://{neo4j_host}:7687",
            "NEO4J_USER": "neo4j",
            "NEO4J_DATABASE": "neo4j",
            "AWS_REGION": Aws.REGION,
            "RECEIPT_STORAGE_BACKEND": "s3",
            "S3_RECEIPT_BUCKET": receipts_bucket.bucket_name,
            "S3_RECEIPT_PREFIX": "receipts",
            "CORS_ALLOWED_ORIGINS": self.node.try_get_context("cors_allowed_origins")
            or f"https://{app_host}",
            "MCP_DEV_TOKEN_AUTH": "false",
            "MCP_ISSUER_URL": issuer_url,
            "MCP_RESOURCE_URL": mcp_url,
            "MCP_JWKS_URL": f"{issuer_url}/.well-known/jwks.json",
            "MCP_JWT_AUDIENCE": mcp_url,
            "MCP_SCOPE_PREFIX": "bobbeori-mcp",
            "MCP_SUPPORTED_SCOPES": ",".join(
                f"bobbeori-mcp/{name}" for name in MCP_SCOPE_NAMES
            ),
            "MCP_REQUIRED_SCOPES": ",".join(
                f"bobbeori-mcp/{name}" for name in MCP_SCOPE_NAMES
            ),
            "GOOGLE_CALENDAR_REDIRECT_URI": self.node.try_get_context(
                "google_calendar_redirect_uri"
            )
            or f"https://{app_host}/auth/callback/google-calendar",
        }
        common_secrets = {
            "DB_USER": ecs.Secret.from_secrets_manager(database.secret, "username"),
            "DB_PASSWORD": ecs.Secret.from_secrets_manager(database.secret, "password"),
            "NEO4J_PASSWORD": ecs.Secret.from_secrets_manager(neo4j_secret, "password"),
            "JWT_SECRET_KEY": ecs.Secret.from_secrets_manager(
                application_secret, "JWT_SECRET_KEY"
            ),
            "MCP_PREVIEW_TOKEN_SECRET": ecs.Secret.from_secrets_manager(
                application_secret, "JWT_SECRET_KEY"
            ),
            "OPENAI_API_KEY": ecs.Secret.from_secrets_manager(
                external_secret, "OPENAI_API_KEY"
            ),
            "GOOGLE_CLIENT_ID": ecs.Secret.from_secrets_manager(
                external_secret, "GOOGLE_CLIENT_ID"
            ),
            "GOOGLE_CLIENT_SECRET": ecs.Secret.from_secrets_manager(
                external_secret, "GOOGLE_CLIENT_SECRET"
            ),
        }

        backend_task, _ = self._task(
            name="backend",
            image=image,
            command=[
                "uvicorn",
                "app.backend.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
                "--proxy-headers",
            ],
            environment=common_environment,
            secrets=common_secrets,
            receipts_bucket=receipts_bucket,
            port=8000,
        )
        mcp_environment = {
            **common_environment,
            "MCP_ALLOWED_HOSTS": mcp_host,
            "MCP_PORT": "8001",
        }
        mcp_task, _ = self._task(
            name="mcp",
            image=image,
            command=[
                "uvicorn",
                "app.backend.mcp.server:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8001",
                "--proxy-headers",
            ],
            environment=mcp_environment,
            secrets=common_secrets,
            receipts_bucket=receipts_bucket,
            port=8001,
        )

        backend_service = ecs.FargateService(
            self,
            "BackendService",
            cluster=cluster,
            task_definition=backend_task,
            desired_count=desired_count,
            assign_public_ip=False,
            security_groups=[app_security_group],
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
        )
        mcp_service = ecs.FargateService(
            self,
            "McpService",
            cluster=cluster,
            task_definition=mcp_task,
            desired_count=desired_count,
            assign_public_ip=False,
            security_groups=[app_security_group],
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
        )

        for service in (backend_service, mcp_service):
            scaling = service.auto_scale_task_count(
                min_capacity=desired_count,
                max_capacity=6 if is_production else 2,
            )
            scaling.scale_on_cpu_utilization(
                "CpuScaling",
                target_utilization_percent=60,
                scale_in_cooldown=Duration.minutes(5),
                scale_out_cooldown=Duration.minutes(1),
            )

        zone = route53.HostedZone.from_hosted_zone_attributes(
            self,
            "PublicHostedZone",
            hosted_zone_id=hosted_zone_id,
            zone_name=root_domain,
        )
        certificate = acm.Certificate(
            self,
            "Certificate",
            domain_name=api_host,
            subject_alternative_names=[mcp_host],
            validation=acm.CertificateValidation.from_dns(zone),
        )
        alb_security_group = ec2.SecurityGroup(
            self,
            "AlbSecurityGroup",
            vpc=vpc,
            allow_all_outbound=True,
        )
        alb_security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(443), "Public HTTPS"
        )
        alb = elbv2.ApplicationLoadBalancer(
            self,
            "LoadBalancer",
            vpc=vpc,
            internet_facing=True,
            security_group=alb_security_group,
            idle_timeout=Duration.seconds(120),
        )
        listener = alb.add_listener(
            "HttpsListener",
            port=443,
            certificates=[certificate],
            default_action=elbv2.ListenerAction.fixed_response(
                status_code=404,
                content_type="application/json",
                message_body='{"detail":"Not found"}',
            ),
        )
        backend_targets = listener.add_targets(
            "BackendTargets",
            port=8000,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[backend_service],
            priority=10,
            conditions=[elbv2.ListenerCondition.host_headers([api_host])],
            health_check=elbv2.HealthCheck(path="/", healthy_http_codes="200"),
            deregistration_delay=Duration.seconds(30),
        )
        mcp_targets = listener.add_targets(
            "McpTargets",
            port=8001,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[mcp_service],
            priority=20,
            conditions=[elbv2.ListenerCondition.host_headers([mcp_host])],
            health_check=elbv2.HealthCheck(
                path="/.well-known/oauth-protected-resource/mcp",
                healthy_http_codes="200",
            ),
            deregistration_delay=Duration.seconds(30),
        )
        app_security_group.add_ingress_rule(
            alb_security_group, ec2.Port.tcp(8000), "Backend from ALB"
        )
        app_security_group.add_ingress_rule(
            alb_security_group, ec2.Port.tcp(8001), "MCP from ALB"
        )
        for record_id, host in (("ApiRecord", api_host), ("McpRecord", mcp_host)):
            route53.ARecord(
                self,
                record_id,
                zone=zone,
                record_name=host,
                target=route53.RecordTarget.from_alias(
                    route53_targets.LoadBalancerTarget(alb)
                ),
            )

        frontend_certificate = acm.DnsValidatedCertificate(
            self,
            "FrontendCertificate",
            domain_name=app_host,
            hosted_zone=zone,
            region="us-east-1",
        )
        frontend_distribution = cloudfront.Distribution(
            self,
            "FrontendDistribution",
            default_root_object="index.html",
            domain_names=[app_host],
            certificate=frontend_certificate,
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(frontend_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD_OPTIONS,
                cached_methods=cloudfront.CachedMethods.CACHE_GET_HEAD_OPTIONS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.minutes(5),
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.minutes(5),
                ),
            ],
        )
        route53.ARecord(
            self,
            "AppRecord",
            zone=zone,
            record_name=app_host,
            target=route53.RecordTarget.from_alias(
                route53_targets.CloudFrontTarget(frontend_distribution)
            ),
        )
        frontend_dist_path = Path(
            self.node.try_get_context("frontend_dist_path")
            or REPO_ROOT / "app/frontend/dist"
        )
        if frontend_dist_path.exists():
            s3deploy.BucketDeployment(
                self,
                "FrontendDeployment",
                sources=[s3deploy.Source.asset(str(frontend_dist_path))],
                destination_bucket=frontend_bucket,
                distribution=frontend_distribution,
                distribution_paths=["/*"],
            )

        calendar_task, _ = self._task(
            name="calendar-sync",
            image=image,
            command=["python", "-m", "app.backend.services.calendar_job"],
            environment=common_environment,
            secrets=common_secrets,
            receipts_bucket=receipts_bucket,
        )
        calendar_dlq = sqs.Queue(
            self,
            "CalendarSyncDlq",
            encryption=sqs.QueueEncryption.SQS_MANAGED,
            retention_period=Duration.days(14),
        )
        scheduler.Schedule(
            self,
            "CalendarSyncSchedule",
            schedule_name=f"bobbeori-{environment_name}-calendar-sync",
            schedule=scheduler.ScheduleExpression.cron(
                minute="0",
                hour="7",
                time_zone=TimeZone.ASIA_SEOUL,
            ),
            target=scheduler_targets.EcsRunFargateTask(
                cluster,
                task_definition=calendar_task,
                assign_public_ip=False,
                vpc_subnets=ec2.SubnetSelection(
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
                ),
                security_groups=[app_security_group],
                dead_letter_queue=calendar_dlq,
                retry_attempts=2,
                max_event_age=Duration.hours(2),
            ),
            description="Run the Bobbeori Google Calendar synchronization at 07:00 KST",
        )

        migration_task, _ = self._task(
            name="migrate",
            image=image,
            command=["python", "-m", "app.backend.jobs.migrate"],
            environment=common_environment,
            secrets=common_secrets,
            receipts_bucket=receipts_bucket,
        )

        CfnOutput(self, "ApiUrl", value=f"https://{api_host}")
        CfnOutput(self, "AppUrl", value=f"https://{app_host}")
        CfnOutput(self, "FrontendBucketName", value=frontend_bucket.bucket_name)
        CfnOutput(
            self,
            "FrontendDistributionDomainName",
            value=frontend_distribution.distribution_domain_name,
        )
        CfnOutput(self, "McpUrl", value=mcp_url)
        CfnOutput(self, "ReceiptBucketName", value=receipts_bucket.bucket_name)
        CfnOutput(self, "CognitoUserPoolId", value=user_pool.user_pool_id)
        CfnOutput(self, "CognitoIssuer", value=issuer_url)
        CfnOutput(self, "OAuthScopes", value=",".join(oauth_scopes))
        CfnOutput(self, "ClusterName", value=cluster.cluster_name)
        CfnOutput(self, "MigrationTaskDefinitionArn", value=migration_task.task_definition_arn)
        CfnOutput(self, "ApplicationSecurityGroupId", value=app_security_group.security_group_id)
        CfnOutput(
            self,
            "ApplicationSubnetIds",
            value=",".join(subnet.subnet_id for subnet in vpc.private_subnets),
        )

    def _create_cognito(
        self,
        *,
        environment_name: str,
        cognito_domain_prefix: str,
        chatgpt_callbacks: list[str],
        codex_callbacks: list[str],
    ) -> tuple[cognito.UserPool, cognito.UserPoolResourceServer, list[str]]:
        user_pool = cognito.UserPool(
            self,
            "UserPool",
            user_pool_name=f"bobbeori-{environment_name}-mcp",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_digits=True,
                require_lowercase=True,
                require_uppercase=True,
                require_symbols=True,
            ),
            removal_policy=RemovalPolicy.RETAIN,
        )
        user_pool.add_domain(
            "Domain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=cognito_domain_prefix
            ),
        )
        scope_objects = [
            cognito.ResourceServerScope(
                scope_name=name,
                scope_description=f"Bobbeori {name} permission",
            )
            for name in MCP_SCOPE_NAMES
        ]
        resource_server = user_pool.add_resource_server(
            "McpResourceServer",
            identifier="bobbeori-mcp",
            scopes=scope_objects,
        )
        oauth_scope_objects = [
            cognito.OAuthScope.resource_server(resource_server, scope)
            for scope in scope_objects
        ]

        clients: dict[str, cognito.UserPoolClient] = {}
        for client_name, callbacks in (
            ("ChatGPT", chatgpt_callbacks),
            ("Codex", codex_callbacks),
        ):
            clients[client_name] = user_pool.add_client(
                f"{client_name}Client",
                user_pool_client_name=f"bobbeori-{environment_name}-{client_name.lower()}",
                generate_secret=False,
                prevent_user_existence_errors=True,
                enable_token_revocation=True,
                access_token_validity=Duration.hours(1),
                supported_identity_providers=[
                    cognito.UserPoolClientIdentityProvider.COGNITO
                ],
                o_auth=cognito.OAuthSettings(
                    flows=cognito.OAuthFlows(authorization_code_grant=True),
                    scopes=[
                        cognito.OAuthScope.OPENID,
                        cognito.OAuthScope.EMAIL,
                        *oauth_scope_objects,
                    ],
                    callback_urls=callbacks,
                    logout_urls=callbacks,
                ),
            )
            CfnOutput(
                self,
                f"{client_name}OAuthClientId",
                value=clients[client_name].user_pool_client_id,
            )

        return (
            user_pool,
            resource_server,
            [f"bobbeori-mcp/{name}" for name in MCP_SCOPE_NAMES],
        )

    def _create_neo4j(
        self,
        *,
        vpc: ec2.Vpc,
        app_security_group: ec2.SecurityGroup,
        environment_name: str,
        is_production: bool,
    ) -> tuple[str, secretsmanager.Secret]:
        secret = secretsmanager.Secret(
            self,
            "Neo4jSecret",
            secret_name=f"bobbeori/{environment_name}/neo4j",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template=json.dumps({"username": "neo4j"}),
                generate_string_key="password",
                password_length=32,
                exclude_punctuation=True,
            ),
        )
        security_group = ec2.SecurityGroup(
            self,
            "Neo4jSecurityGroup",
            vpc=vpc,
            allow_all_outbound=True,
        )
        security_group.add_ingress_rule(
            app_security_group,
            ec2.Port.tcp(7687),
            "Bolt from Bobbeori tasks",
        )
        role = iam.Role(
            self,
            "Neo4jRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                )
            ],
        )
        secret.grant_read(role)
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "dnf install -y docker jq",
            "systemctl enable --now docker",
            (
                "NEO4J_PASSWORD=$(aws secretsmanager get-secret-value "
                f"--secret-id '{secret.secret_arn}' --region '{Aws.REGION}' "
                "--query SecretString --output text | jq -r .password)"
            ),
            "mkdir -p /var/lib/neo4j-data",
            (
                "docker run -d --name neo4j --restart always -p 7687:7687 "
                "-v /var/lib/neo4j-data:/data "
                "-e NEO4J_AUTH=neo4j/${NEO4J_PASSWORD} "
                "-e NEO4J_server_memory_heap_initial__size=512m "
                "-e NEO4J_server_memory_heap_max__size=1G "
                "neo4j:5.26-community"
            ),
        )
        instance = ec2.Instance(
            self,
            "Neo4jInstance",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_group=security_group,
            role=role,
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            instance_type=ec2.InstanceType(
                "t3.large" if is_production else "t3.medium"
            ),
            require_imdsv2=True,
            user_data=user_data,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        80 if is_production else 40,
                        encrypted=True,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        delete_on_termination=not is_production,
                    ),
                )
            ],
        )
        private_zone = route53.PrivateHostedZone(
            self,
            "PrivateHostedZone",
            zone_name=f"{environment_name}.bobbeori.internal",
            vpc=vpc,
        )
        host = f"neo4j.{private_zone.zone_name}"
        route53.ARecord(
            self,
            "Neo4jRecord",
            zone=private_zone,
            record_name="neo4j",
            target=route53.RecordTarget.from_ip_addresses(instance.instance_private_ip),
        )
        return host, secret

    def _task(
        self,
        *,
        name: str,
        image: ecs.ContainerImage,
        command: list[str],
        environment: dict[str, str],
        secrets: dict[str, ecs.Secret],
        receipts_bucket: s3.Bucket,
        port: int | None = None,
    ) -> tuple[ecs.FargateTaskDefinition, ecs.ContainerDefinition]:
        normalized_name = "".join(part.title() for part in name.split("-"))
        task = ecs.FargateTaskDefinition(
            self,
            f"{normalized_name}Task",
            cpu=1024,
            memory_limit_mib=2048,
        )
        receipts_bucket.grant_read_write(task.task_role)
        log_group = logs.LogGroup(
            self,
            f"{normalized_name}LogGroup",
            log_group_name=f"/bobbeori/{self.node.try_get_context('environment') or 'dev'}/{name}",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )
        container = task.add_container(
            f"{normalized_name}Container",
            image=image,
            command=command,
            environment=environment,
            secrets=secrets,
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix=name,
                log_group=log_group,
            ),
        )
        if port is not None:
            container.add_port_mappings(
                ecs.PortMapping(container_port=port, protocol=ecs.Protocol.TCP)
            )
        return task, container

    def _required_context(self, name: str) -> str:
        value = self.node.try_get_context(name)
        if not value:
            raise ValueError(f"CDK context '{name}' is required")
        return str(value)

    def _context_list(self, name: str, *, required: bool = False) -> list[str]:
        value = self.node.try_get_context(name)
        if isinstance(value, list):
            result = [str(item).strip() for item in value if str(item).strip()]
        else:
            result = [item.strip() for item in str(value or "").split(",") if item.strip()]
        if required and not result:
            raise ValueError(f"CDK context '{name}' is required")
        return result
