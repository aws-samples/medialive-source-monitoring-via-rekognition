#!/bin/bash

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0


# Script to build and upload Docker image to ECR
# Run with no arguments to automatically obtain account data.
# If script is unable to obtain details, supply them manually:
# eg.
#   create_container.sh 123456789012 eu-west-1


# Image name for container
ImageName="emlsourcewatcher"
# Repository Name
RepositoryName="medialive_source_monitoring_via_rekognition"

# Get account number
AccountNum=$1
if [[ -z "$AccountNum" ]]; then
    echo "Obtaining account number..."
    AccountNum=$(aws sts get-caller-identity --query "Account" --output text)
fi
echo "Using Account: ${AccountNum}"

# Get region
Region=$2
if [[ -z "$Region" ]]; then
    echo "Obtaining region..."
    Region=$(aws configure get region)
fi
echo "Using Region: ${Region}"

# Continue only if account data is available
if [[ -n "$AccountNum" ]] || [[ -n "$Region" ]]; then
    # Builder Docker image
    echo "Building Docker image..."
    docker build -t "${ImageName}:latest" .

    # Authenticate to ECR
    echo "Authenticating to ECR..."
    aws ecr get-login-password --region "${Region}" | docker login --username AWS --password-stdin "${AccountNum}.dkr.ecr.eu-west-1.amazonaws.com"

    # Create ECR repository
    echo "Creating ECR repository..."
    aws ecr create-repository --repository-name "${RepositoryName}"  --image-scanning-configuration scanOnPush=true --region "${Region}"

    # Tag Docker image for upload
    echo "Tagging Docker image for upload..."
    docker tag "${ImageName}:latest" "${AccountNum}.dkr.ecr.eu-west-1.amazonaws.com/${RepositoryName}"

    # Push Image to ECR
    echo "Pushing Docker image to ECR..."
    docker push "${AccountNum}.dkr.ecr.eu-west-1.amazonaws.com/${RepositoryName}:latest"
    echo "Done!"
else
    echo "Unable to automatically obtain account data."
    echo "Please run script again, but manually supply account number and region"
    echo "eg. create_container.sh 123456789012 eu-west-1"
fi
