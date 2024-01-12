# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

# Namespace in CloudWatch to group the metrics under
MetricNamespace = "EmlRekognitionWatcher"

# How often to poll for thumbnails in seconds
DetectionInterval = 10

# SQS Queue name to solution will create
SqsQueue = "MediaLiveRekognitionSQS"

# Container image to use from ECR created by the build script
EcrRepository = "medialive_source_monitoring_via_rekognition"

# Enable DEBUG Python logging in container for verbose logging
EnableDebug = True
