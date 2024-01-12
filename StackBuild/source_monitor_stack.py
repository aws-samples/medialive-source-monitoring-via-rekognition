# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0


import aws_cdk as cdk
import StackBuild.config as config
from cdk_nag import NagSuppressions, NagPackSuppression, AwsSolutionsChecks
from aws_cdk import (
    Aspects,
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecr as ecr,
    aws_iam as iam,
    aws_sqs as sqs,
    aws_logs as logs,
    aws_events as events,
    aws_events_targets as targets,
)
from constructs import Construct

class EmlRekognitionStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        env_vars={
                "METRIC_NAMESPACE": config.MetricNamespace,
                "DETECTION_INTERVAL" : str(config.DetectionInterval),
                "SQS_QUEUE_NAME": config.SqsQueue,
                "ECS_AVAILABLE_LOGGING_DRIVERS" : '["json-file","awslogs"]'
            }
        if config.EnableDebug:
            env_vars["ENABLE_DEBUG"] = "True"

        # Create SQS Queue
        queue = sqs.Queue(
            self,
            "EmlRekognitionSqsQueue",
            queue_name=config.SqsQueue,
            retention_period=cdk.Duration.minutes(5),
            enforce_ssl=True
        )

        # Create EventBridge Rule
        rule = events.Rule(self,
            "EmlRekognitionRule",
            rule_name="eml_rekognition_eml_state_change_rule",
            event_bus=events.EventBus.from_event_bus_name(self, "DefaultEventBus", "default"),
            event_pattern=events.EventPattern(
                source=["aws.medialive"],
                detail_type=["MediaLive Channel State Change"]
            )
        )
        rule.add_target(targets.SqsQueue(queue))

        # Create VPC flow logs and associated IAM role
        vpc_log_role=iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=["*"],
            actions=[
                "logs:CreateLogStream",
                "logs:PutLogEvents",
                "logs:CreateLogGroup",
            ]
        )
        vpc_log_group = logs.LogGroup(self,
            "EmlRekognitionVpcFlowLogGroup",
            log_group_name="eml_rekognition_vpc_flow_logs"
        )
        vpc_log_role = iam.Role(self,
            "EmlRekognitionVpcCustomRole",
            assumed_by=iam.ServicePrincipal("vpc-flow-logs.amazonaws.com"
            )
        )

        # Create VPC
        vpc = ec2.Vpc(
            self,
            "EmlRekognitionVpc",
            max_azs=1
        )
        flow_logs=ec2.FlowLog(self,
            "eml_rekognition_vpc_flow_logs",
            resource_type=ec2.FlowLogResourceType.from_vpc(vpc),
            destination=ec2.FlowLogDestination.to_cloud_watch_logs(
                log_group=vpc_log_group,
                iam_role=vpc_log_role
            )
        )

        # Create cluster
        cluster = ecs.Cluster(
            self,
            'EmlRekognitionCluster',
            vpc=vpc,
            container_insights=True
        )

        # Create IAM execution role
        execution_role = iam.Role(
            self,
            "EmlRekognitionExecutionRole",
            assumed_by=iam.ServicePrincipal(
                "ecs-tasks.amazonaws.com"
            ),
            role_name="eml-rekognition-execution-role"
        )
        execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                resources=[f"arn:aws:ecs:{self.region}:{self.account}:task-definition/eml-rekognition-task:*"],
                actions=[
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:CreateLogGroup",
                ]
            )
        )

        # Create task role
        task_role = iam.Role(
            self,
            "EmlRekognitionEcsTaskRole",
            assumed_by=iam.ServicePrincipal(
                "ecs-tasks.amazonaws.com"
                ),
            role_name="eml-rekognition-task-role"
            )
        task_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                resources=[
                    f"arn:aws:sqs:{self.region}:{self.account}:{config.SqsQueue}",
                    f"arn:aws:ecs:{self.region}:{self.account}:task-definition/eml-rekognition-task:*",
                    f"arn:aws:medialive:{self.region}:{self.account}:channel:*",
                    ],
                actions=[
                    "sqs:ReceiveMessage",
                    "sqs:DeleteMessage",
                    "sqs:GetQueueUrl",
                    "medialive:ListChannels",
                    "medialive:DescribeThumbnails"
                ]
            )
        )
        task_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                resources=["*"],
                actions=[
                    "rekognition:DetectLabels",
                    "cloudwatch:PutMetricData"
                    ]
            )
        )

        # Create task definition
        task_definition = ecs.FargateTaskDefinition(
            self,
            "EmlRekognitionTaskDefinition",
            execution_role=execution_role,
            task_role=task_role,
            family="eml-rekognition-task",
            cpu=256
        )

        # Add container to task
        repository = ecr.Repository.from_repository_name(
            self,
            "EmlRekognitionRepository",
            config.EcrRepository
        )
        container = task_definition.add_container(
            "EmlRekognitionContainer",
            image=ecs.ContainerImage.from_ecr_repository(repository),
            logging=ecs.AwsLogDriver(stream_prefix="eml_rekognition_task_logs"),
            environment=env_vars
        )

        # Create Fargate Service
        service = ecs.FargateService(
            self,
            "EmlRekognitionService",
            cluster=cluster,
            task_definition=task_definition,
            service_name="eml-rekognition-service"
        )

        NagSuppressions.add_resource_suppressions(
            construct=self,
            suppressions=[
                    NagPackSuppression(
                    id="AwsSolutions-SQS3",
                    reason="Dead Letter Queue recommended but as this is a basic example we will skip using one",
                ),
                    NagPackSuppression(
                    id="AwsSolutions-ECS2",
                    reason="Recommended to use Secrets Manager, but as this is a basic example and it's only basic configuration setup supplied we will skip using one here for brevity",
                ),
                    NagPackSuppression(
                    id="AwsSolutions-IAM5",
                    reason="Wildcard scoped to the task definition",
                )
            ],
            apply_to_children=True,
        )

        Aspects.of(self).add(AwsSolutionsChecks(verbose=True))
