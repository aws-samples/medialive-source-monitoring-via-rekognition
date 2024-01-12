# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import base64
import boto3
import json
import logging
import os
import sys
from datetime import datetime
from time import sleep
from time import time
from random import randint
from threading import Thread
from threading import Event


class EMLRekognitionCLass:
    def __init__(self, ChannelId, PipelineNum, EventFlag):
        self.ChannelId = ChannelId
        self.PipelineNum = PipelineNum
        self.EventFlag = EventFlag

    # Thread per channel to obtain thumbnails and run Rekognition
    def Detection_Thread(self):
        log.debug(f"Thread started for {self.ChannelId}:{self.PipelineNum}") 
        wait_loop_cpu_sleep_duration=0.5

        # For difference check
        PreviousImageValue = -1

        while True:
            start_time = time()
            # Obtain thumbnail from MediaLive Pipeline
            JpegBodyDict = self.Request_Thumbnail()

            if JpegBodyDict:
                # Decode JSON response to JPEG binary
                JpegImage=base64.b64decode(JpegBodyDict)

                # Run Rekognition
                ImageValue = self.Detect_Image_Values(JpegImage)

                # Post Data
                if ImageValue:
                    if PreviousImageValue > -1:
                        Difference = abs(ImageValue - PreviousImageValue)
                        self.Send_To_CloudWatch(Difference)
                    PreviousImageValue = ImageValue
                else:
                    # Error in Rekognition so invalidate for next difference check
                    PreviousImageValue = -1
            else:
                log.warning(f"Empty thumbnail returned for {self.ChannelId}:{self.PipelineNum}")
                # Error obtaining thumbnail so invalidate for next difference check
                PreviousImageValue = -1
            # Wait for remaining time
            while time()-start_time<Detection_Interval and not self.EventFlag.is_set():
                sleep(wait_loop_cpu_sleep_duration)
            if self.EventFlag.is_set():
                log.debug(f"{self.ChannelId}:{self.PipelineNum} thread exiting")
                break
        return


    # Pull thumbnail from MediaLive Pipeline
    def Request_Thumbnail(self):
        Thumbnail = None
        try:
            eml = boto3.client("medialive") 
            jpegjson = eml.describe_thumbnails(
                ChannelId = str(self.ChannelId),
                PipelineId = str(self.PipelineNum),
                ThumbnailType = 'CURRENT_ACTIVE'
            )
            Thumbnail = jpegjson["ThumbnailDetails"][0]["Thumbnails"][0]["Body"]
        except Exception as e:
            log.error(f"Unknown error {e} in Request_Thumbnail for {self.ChannelId}:{self.PipelineNum}")
        return Thumbnail


    # Run rekognition for each pipeline source thumbnail
    def Detect_Image_Values(self, JpegImages):
        rekognition_client = boto3.client('rekognition')
        try:
            response = rekognition_client.detect_labels(
                Image = {'Bytes': JpegImages},
                Features = ["IMAGE_PROPERTIES"]
                )["ImageProperties"]["Quality"]
            ImageValues  = int(response["Brightness"]+response["Sharpness"]+response["Contrast"])
        except Exception as e:
            log.error(f"Error invoking Rekognition - {e}")
            return None
        else:
            return ImageValues


    def Send_To_CloudWatch(self, ImageValue):
        try:
            cloudwatch = boto3.client('cloudwatch')
            cloudwatch.put_metric_data(
                MetricData=[
                    {
                        'MetricName': 'ImageProperties',
                        'Value': ImageValue,
                        'Unit': "None",
                        'StorageResolution': 1,
                        'Timestamp': datetime.now(),
                        'Dimensions': [
                            {
                                'Name': 'ChannelId',
                                'Value': str(self.ChannelId)
                            },
                            {
                                'Name': 'Pipeline',
                                'Value': str(self.PipelineNum)
                            }
                        ]
                    }
                ],
                Namespace = Namespace
            )
        except Exception as e:
            log.error(f"Error posting to CloudWatch - {e}")
            raise
        return


# Obtain list of active channels
def Retrieve_MediaLive_Channel_List():
    ActiveChannelList = []
    try:
        eml = boto3.client("medialive")
        paginator = eml.get_paginator('list_channels')
        for EmlChannelList in paginator.paginate():
            for EmlChannel in EmlChannelList["Channels"]:
                ChannelState = EmlChannel['State']
                if ChannelState == "RUNNING" or ChannelState == "STARTING":
                    ChannelID = EmlChannel['Arn'].split(":")[6]
                    PipelinesRunning = EmlChannel['PipelinesRunningCount']
                    ActiveChannelList.append( {"ChannelId" : ChannelID, "ChannelPipelines" : PipelinesRunning} )
    except Exception as e:
        log.error(f"Error retrieving channel list - {e}")
    return ActiveChannelList


# Start threads for each channel
def Start_Channel_Detection_Threads_From_List(ChannelId, NumpipeLines):
    for x in range(NumpipeLines):
        log.info(f"Starting thread for channel {ChannelId} pipeline {x}")
        Start_Detection_Thread(ChannelId, x-1)
    return


# Start single thread
def Start_Detection_Thread(ChannelId, PipelineNum):
    log.debug(f"Start thread requested {ChannelId}:{PipelineNum}")
    for item in ThreadList:
        if item["ChannelId"] == ChannelId and item["PipelineId"] == PipelineNum:
            log.debug(f"Already in list {ChannelId}:{PipelineNum} - skipping")
            return
    event = Event()
    thread = Thread(target=EMLRekognitionCLass(ChannelId, PipelineNum, event).Detection_Thread, args=())
    thread.start()
    ThreadList.append( {"ChannelId" : ChannelId, "PipelineId" : PipelineNum, "Thread" : thread, "EventFlag" : event} )
    log.info(f"Thread started {ChannelId}:{PipelineNum}")
    return


# Stop single thread
def Stop_Detection_Thread(ChannelId, PipelineNum):
    log.debug(f"Stop thread requested {ChannelId}:{PipelineNum}")
    for num, item in enumerate(ThreadList):
        if item["ChannelId"] == ChannelId and item["PipelineId"] == PipelineNum:
            item["EventFlag"].set()
            log.info(f"Thread stopped {ChannelId}:{PipelineNum}")
            del ThreadList[num]
            break
    return


# Main work loop
def Work_Loop():   
    log.info("Beginning main loop")
    sqs = boto3.resource('sqs')
    queue = sqs.get_queue_by_name(QueueName=SQS_Queue)
    while True:
        try:
            for message in queue.receive_messages(WaitTimeSeconds=20):
                msgjson = json.loads(message.body)
                ChannelId = int(msgjson["resources"][0].split(":")[6])
                ChannelState = msgjson["detail"]["state"]
                ChannelPipelineNum = int(msgjson["detail"]["pipeline"])

                if ChannelState == "STARTING" or ChannelState == "RUNNING":
                    Start_Detection_Thread(ChannelId, ChannelPipelineNum)

                if ChannelState == "STOPPING" or ChannelState == "STOPPED":
                    Stop_Detection_Thread(ChannelId, ChannelPipelineNum)
                    # Sometimes pipeline 1 stop not sent - covering this below
                    if ChannelPipelineNum == 0:
                        Stop_Detection_Thread(ChannelId, 1)
                message.delete()
        except Exception as e:
            log.error(f"Error reading SQS message- {e}")
    return


# Entry Point
if __name__ == "__main__":
    log = logging.getLogger(__name__)
    logging.basicConfig( stream=sys.stderr, level=logging.WARNING )
    log.info("Starting")

    if "ENABLE_DEBUG" in os.environ:
        log.setLevel(logging.DEBUG)
        log.debug("Debug logging enabled")
    Namespace = os.environ.get('METRIC_NAMESPACE')
    Detection_Interval = int(os.environ.get('DETECTION_INTERVAL'))
    SQS_Queue = os.environ.get('SQS_QUEUE_NAME')
    log.info(f"Using namespace {Namespace} at interval {Detection_Interval} with queue {SQS_Queue}")

    # Start threads for all currently active channels
    Active_Channel_List = Retrieve_MediaLive_Channel_List()
    ThreadList = []
    for EmlChannel in Active_Channel_List:
        for EmlPipe in range(EmlChannel["ChannelPipelines"]):            
            Start_Detection_Thread(int(EmlChannel["ChannelId"]), int(EmlPipe))            
            # Small delay to spread thumbnail api requests
            sleep(randint(1,Detection_Interval-1))

    Work_Loop()
    log.info("Exited")
