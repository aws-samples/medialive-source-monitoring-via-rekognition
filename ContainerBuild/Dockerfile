# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

FROM amazonlinux:latest
LABEL maintainer="andchand@amazon.co.uk"

RUN yum install python-devel python-pip python3-setuptools git -y && \
    git clone https://github.com/boto/boto3.git && \
    cd boto3 && \
    python3 -m pip install -r requirements.txt && \
    python3 -m pip install -e .

COPY EmlToRekognition.py /home/EmlToRekognition.py

CMD python3 /home/EmlToRekognition.py    
