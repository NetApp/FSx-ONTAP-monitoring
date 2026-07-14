#!/usr/bin/python3
#
# This script is used to add CloudWatch alarms for all the FSx for NetApp
# ONTAP volumes, that don't already have one, that will trigger when the
# utilization of the volume gets above the threshold defined below. It will
# also create an alarm that will trigger when the file system reach
# an average CPU utilization greater than what is specified below as well
# an alarm that will trigger when the SSD utilization is greater than what
# is specified below.
#
# It can either be run as a standalone script, or uploaded as a Lambda
# function with the thought being that you will create a EventBridge schedule
# to invoke it periodically.
#
# It will scan all regions looking for FSxN volumes and file systems
# and since CloudWatch can't send SNS messages across regions, it assumes
# that the specified SNS topic exist in each region for the specified
# account ID.
#
# Finally, a default volume threshold is defined below. It sets the volume
# utilization threshold that will cause CloudWatch to send the alarm event
# to the SNS topic. It can be overridden on a per volume basis by having a
# tag with the name of "alarm_threshold" set to the desired threshold.
# If the tag is set to 100, then no alarm will be created. You can also
# set an override to the filesystem CPU utilization alarm, but setting
# a tag with the name of 'CPU_Alarm_Threshold' on the file system resouce.
# Lastly, you can create an override for the SSD alarm, by creating a tag
# with the name "SSD_Alarm_Threshold" on the file system resource.
#
# Version: %%VERSION%%
# Date: %%DATE%%
#
################################################################################
#
# The following variables effect the behavior of the script. They can be
# either be set here, overridden via the command line options, or
# overridden by environment variables.
#
# Define which SNS topic you want alerts to sent to. Since CloudWatch can't
# post messages to SNS Topics in other regions, this topic should
# exist in all regions that you want to monitor. 
SNStopic=''
#
# Define the AWS account ID that the SNS topic is in. This is used to
# create the ARN for the SNS topic so CloudWatch can send messages to it.
accountId=''
#
# Set the customer ID associated with the AWS account. This is used to
# as part of the alarm name prefix so a customer ID can be associated
# with the alarm. If it is left as an empty string, no extra prefix
# will be added.
customerId=''
#
# Define the default CPU utilization threshold before sending the alarm.
# Setting it to 100 will disable the creation of the alarm.
defaultCPUThreshold=80
#
# Define the default disk throughput utilization threshold before sending the alarm.
# Setting it to 100 will disable the creation of the alarm.
defaultDiskThroughputThreshold=80
#
# Define the default disk IOPS utilization threshold before sending the alarm.
# Setting it to 100 will disable the creation of the alarm.
defaultDiskIOPSThreshold=80
#
# Define the default network throuhput utilization threshold before sending the alarm.
# Setting it to 100 will disable the creation of the alarm.
defaultNetworkThroughputThreshold=80
#
# Define the default SSD utilization threshold before sending the alarm.
# Setting it to 100 will disable the creation of the alarm.
defaultSSDThreshold=90
#
# Define the default volume utilization threshold before sending the alarm.
# Setting it to 100 will disable the creation of the alarm.
defaultVolumeThreshold=80
#
# Define the default volume files utilization threshold before sending the alarm.
# Setting it to 100 will disable the creation of the alarm.
defaultVolumeFilesThreshold=100
#
################################################################################
# You can't change the following variables from the command line or environment
# variables since changing them after the program has run once would cause
# all existing CloudWatch alarms to be abandoned, and all new alarms to be
# created. So, it is not recommended to change these variables unless you know
# what you are doing.
################################################################################
#
# The following is put in front of all alarms so an IAM policy can be create
# that will allow this script to only be able to delete the alarms it creates.
# If you change this, you must also change the IAM policy. It can be
# set via an environment variable, this is so that the CloudFormation template
# can pass the value to the Lambda function. To change the value, change
# the "FSx-ONTAP-Auto" string to your desired value.
import os
basePrefix = os.environ.get('basePrefix', "FSx-ONTAP-Auto")
#
# Define the prefix for the volume utilization alarm name for the CloudWatch alarms.
alarmPrefixVolume=f"{basePrefix}-Volume_Utilization_for_volume_"
#
# Define the prefix for the volume files utilization alarm name for the CloudWatch alarms.
alarmFilesPrefixVolume=f"{basePrefix}-Volume_Files_Utilization_for_volume_"
#
# Define the prefix for the CPU utilization alarm name for the CloudWatch alarms.
alarmPrefixCPU=f"{basePrefix}-CPU_Utilization_for_fs_"
#
# Define the prefix for the Disk Throughput utilization alarm name for the CloudWatch alarms.
alarmPrefixDiskThroughput=f"{basePrefix}-Disk_Throughput_Utilization_for_fs_"
#
# Define the prefix for the Disk IOPS utilization alarm name for the CloudWatch alarms.
alarmPrefixDiskIOPS=f"{basePrefix}-Disk_IOPS_Utilization_for_fs_"
#
# Define the prefix for the Network Throughput utilization alarm name for the CloudWatch alarms.
alarmPrefixNetworkThroughput=f"{basePrefix}-Network_Throughput_Utilization_for_fs_"
#
# Define the prefix for the SSD utilization alarm name for the CloudWatch alarms.
alarmPrefixSSD=f"{basePrefix}-SSD_Utilization_for_fs_"

################################################################################
# You shouldn't have to modify anything below here.
################################################################################

import botocore
from botocore.config import Config
import boto3
import getopt
import sys
import time
import json

################################################################################
# This function adds a file system utilization CloudWatch alarm. It is used
# for the CPU, Disk Throughput, Disk IOPS, and Network Throughput alarms.
################################################################################
def add_file_system_utilization_alarm(cw, fsId, alarmMetric, alarmName, alarmDescription, threshold, region):
    if not dryRun:
        action = f'arn:aws:sns:{region}:{accountId}:{SNStopic}'
        cw.put_metric_alarm(
            AlarmName=alarmName,
            ActionsEnabled=True,
            AlarmActions=[action],
            AlarmDescription=alarmDescription,
            EvaluationPeriods=1,
            DatapointsToAlarm=1,
            Threshold=threshold,
            ComparisonOperator='GreaterThanThreshold',
            MetricName=alarmMetric,
            Period=300,
            Statistic="Average",
            Namespace="AWS/FSx",
            Dimensions=[{'Name': 'FileSystemId', 'Value': fsId}]
        )
    else:
        print(f'Would have added {alarmMetric} alarm for {fsId} with name {alarmName} with threshold of {threshold} in {region} with action {action}')

################################################################################
# This function adds the SSD Utilization CloudWatch alarm.
################################################################################
def add_ssd_alarm(cw, fsId, alarmName, alarmDescription, threshold, region):
    if not dryRun:
        action = f'arn:aws:sns:{region}:{accountId}:{SNStopic}'
        cw.put_metric_alarm(
            AlarmName=alarmName,
            ActionsEnabled=True,
            AlarmActions=[action],
            AlarmDescription=alarmDescription,
            EvaluationPeriods=1,
            DatapointsToAlarm=1,
            Threshold=threshold,
            ComparisonOperator='GreaterThanThreshold',
            MetricName="StorageCapacityUtilization",
            Period=300,
            Statistic="Average",
            Namespace="AWS/FSx",
            Dimensions=[{'Name': 'FileSystemId', 'Value': fsId}, {'Name': 'StorageTier', 'Value': 'SSD'}, {'Name': 'DataType', 'Value': 'All'}]
        )
    else:
        print(f'Would have added SSD alarm for {fsId} with name {alarmName} with threshold of {threshold} in {region} with action {action}')

################################################################################
# This function adds the Volume files utilization CloudWatch alarm.
################################################################################
def add_volume_files_alarm(cw, volumeId, alarmName, alarmDescription, fsId, threshold, region):
    if not dryRun:
        action = f'arn:aws:sns:{region}:{accountId}:{SNStopic}'
        cw.put_metric_alarm(
            ActionsEnabled=True,
            AlarmName=alarmName,
            AlarmActions=[action],
            AlarmDescription=alarmDescription,
            EvaluationPeriods=1,
            DatapointsToAlarm=1,
            Threshold=threshold,
            ComparisonOperator='GreaterThanThreshold',
            Namespace="AWS/FSx",
            Metrics=[{"Id":"e1","Label":"Utilization","ReturnData":True,"Expression":"m2/m1*100"},\
                     {"Id":"m2","ReturnData":False,"MetricStat":{"Metric":{"MetricName":"FilesUsed","Dimensions":[{"Name":"VolumeId","Value": volumeId},{"Name":"FileSystemId","Value":fsId}]},"Period":300,"Stat":"Average"}},\
                     {"Id":"m1","ReturnData":False,"MetricStat":{"Metric":{"MetricName":"FilesCapacity","Dimensions":[{"Name":"VolumeId","Value": volumeId},{"Name":"FileSystemId","Value":fsId}]},"Period":300,"Stat":"Average"}}]
        )
    else:
        print(f'Would have added files capacity utilization alarm for {volumeId} {fsId} with name {alarmName} with threshold of {threshold} in {region} with action {action}.')

################################################################################
# This function adds the Volume utilization CloudWatch alarm.
################################################################################
def add_volume_alarm(cw, volumeId, alarmName, alarmDescription, fsId, threshold, region):
    if not dryRun:
        action = f'arn:aws:sns:{region}:{accountId}:{SNStopic}'
        cw.put_metric_alarm(
            ActionsEnabled=True,
            AlarmName=alarmName,
            AlarmActions=[action],
            AlarmDescription=alarmDescription,
            EvaluationPeriods=1,
            DatapointsToAlarm=1,
            Threshold=threshold,
            ComparisonOperator='GreaterThanThreshold',
            Namespace="AWS/FSx",
            Metrics=[{"Id":"e1","Label":"Utilization","ReturnData":True,"Expression":"m2/m1*100"},\
                     {"Id":"m2","ReturnData":False,"MetricStat":{"Metric":{"MetricName":"StorageUsed","Dimensions":[{"Name":"VolumeId","Value": volumeId},{"Name":"FileSystemId","Value":fsId}]},"Period":300,"Stat":"Average"}},\
                     {"Id":"m1","ReturnData":False,"MetricStat":{"Metric":{"MetricName":"StorageCapacity","Dimensions":[{"Name":"VolumeId","Value": volumeId},{"Name":"FileSystemId","Value":fsId}]},"Period":300,"Stat":"Average"}}]
        )
    else:
        print(f'Would have added volume capacity utilization alarm for {volumeId} {fsId} with name {alarmName} with threshold of {threshold} in {region} with action {action}.')


################################################################################
# This function deletes a CloudWatch alarm.
################################################################################
def delete_alarm(cw, alarmName):
    if not dryRun:
        cw.delete_alarms(AlarmNames=[alarmName])
    else:
        print(f'Would have deleted alarm {alarmName}.')

################################################################################
# This function checks to see if the alarm already exists.
################################################################################
def contains_alarm(alarmName, alarms):
    for alarm in alarms:
        if(alarm['AlarmName'] == alarmName):
            return True
    return False

################################################################################
# This function checks to see if a volume exists.
################################################################################
def contains_volume(volumeId, volumes):
    for volume in volumes:
        if(volume['VolumeId'] == volumeId):
            return True
    return False

################################################################################
# This function checks to see if a file system exists.
################################################################################
def contains_fs(fsId, fss):
    for fs in fss:
        if(fs['FileSystemId'] == fsId):
            return True
    return False

################################################################################
# This function checks to see if the passed in threshold tage exist, and if so
# returns the value of the tag.  If not, it returns the default threshold value.
################################################################################
def getAlarmThresholdTagValue(tags, arn, targetTag, defaultThreshold):
    for resource in tags:
        if resource['ResourceARN'] == arn:
            for tag in resource['Tags']:
                if tag['Key'].lower() == targetTag.lower():
                    return tag['Value']

    return defaultThreshold

################################################################################
# This function returns the file system id that the passed in alarm is
# associated with.
################################################################################
def getFileSystemId(alarm):

    for metric in alarm['Metrics']:
        if metric["Id"] == "m1":
            for dim in metric['MetricStat']['Metric']['Dimensions']:
                if dim['Name'] == 'FileSystemId':
                    return dim['Value']
    return None

################################################################################
# This function will returns all the tags associated with the fsx resource
# type.
################################################################################
def getTags(tagsClient):
    #
    # The initial amount of time to sleep if there is a rate limit exception.
    sleep=.125
    while True:
        try:
            response = tagsClient.get_resources(ResourceTypeFilters=['fsx'], ResourcesPerPage=100)
            tags = response['ResourceTagMappingList']
            nextToken = response.get('PaginationToken', "")
            sleep=.125
            break
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'TooManyRequestsException' or e.response['Error']['Code'] == 'ThrottlingException':
                sleep = sleep * 2   # Exponential backoff.
                if sleep > 5:
                    raise e
                print(f"Warning: Rate Limit fault while getting initial tag list. Sleeping for {sleep} seconds.")
                time.sleep(sleep)
            else:
                print(f"boto3 client error: {json.dumps(e.response)}")
                raise e

    while nextToken != "":
        try:
            response = tagsClient.get_resources(ResourceTypeFilters=['fsx'], ResourcesPerPage=100, PaginationToken=nextToken)
            tags += response['ResourceTagMappingList']
            nextToken = response.get('PaginationToken', "")
            sleep=.125
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'TooManyRequestsException' or e.response['Error']['Code'] == 'ThrottlingException':
                sleep = sleep * 2   # Exponential backoff.
                if sleep > 5:
                    raise e
                print(f"Warning: Rate Limit fault while getting tag list. Sleeping for {sleep} seconds.")
                time.sleep(sleep)
            else:
                print(f"boto3 client error: {json.dumps(e.response)}")
                raise e
    return tags

################################################################################
# This function will return all the file systems in the region. It will handle
# the case where there are more file systms than can be returned in a single
# call. It will also handle the case where we get a rate limit exception.
################################################################################
def getFss(fsx):

    # The initial amount of time to sleep if there is a rate limit exception.
    sleep=.125
    while True:
        try:
            response = fsx.describe_file_systems()
            fss = response['FileSystems']
            nextToken = response.get('NextToken', "")
            sleep=.125
            break
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'TooManyRequestsException' or e.response['Error']['Code'] == 'ThrottlingException':
                sleep = sleep * 2   # Exponential backoff.
                if sleep > 5:
                    raise e
                print(f"Warning: Rate Limit fault while getting initial file system list. Sleeping for {sleep} seconds.")
                time.sleep(sleep)
            elif e.response['Error']['Code'] == 'InternalFailure':
                print(f"Warning: boto3 returned a InternalFailure client error while getting initial file system list. Skipping...")
                return []
            else:
                print(f"boto3 client error: {json.dumps(e.response)}")
                raise e
        #
        # These are the exceptions that have been observed being thrown when a region is offline.
        except (botocore.exceptions.ReadTimeoutError, botocore.exceptions.ConnectTimeoutError, botocore.exceptions.ConnectionClosedError) as e:
            print(f"Warning: boto3 client error while getting initial file system list. Exception: {e}. Skipping...")
            return []

    while nextToken != "":
        try:
            response = fsx.describe_file_systems(NextToken=nextToken)
            fss += response['FileSystems']
            nextToken = response.get('NextToken')
            sleep=.125
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'TooManyRequestsException' or e.response['Error']['Code'] == 'ThrottlingException':
                sleep = sleep * 2   # Exponential backoff.
                if sleep > 5:
                    raise e
                print(f"Warning: Rate Limit fault while getting additional file systems. Sleeping for {sleep} seconds.")
                time.sleep(sleep)
            else:
                print(f"boto3 client error: {json.dumps(e.response)}")
                raise e
    return fss

################################################################################
# This function will return all the volumes in the region. It will handle the
# case where there are more volumes than can be returned in a single call.
# It will also handle the case where we get a rate limit exception.
################################################################################
def getVolumes(fsx):
    #
    # The initial amount of time to sleep if there is a rate limit exception.
    sleep=.125
    while True:
        try:
            response = fsx.describe_volumes()
            volumes = response['Volumes']
            nextToken = response.get('NextToken', "")
            sleep=.125
            break
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'TooManyRequestsException' or e.response['Error']['Code'] == 'ThrottlingException':
                sleep = sleep * 2   # Exponential backoff.
                if sleep > 5:
                    raise e
                print(f"Warning: Rate Limit fault while getting the initial list of volumes. Sleeping for {sleep} seconds.")
                time.sleep(sleep)
            else:
                print(f"boto3 client error: {json.dumps(e.response)}")
                raise e

    while nextToken != "":
        try:
            response = fsx.describe_volumes(NextToken=nextToken)
            volumes += response['Volumes']
            nextToken = response.get('NextToken', "")
            sleep=.125
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'TooManyRequestsException' or e.response['Error']['Code'] == 'ThrottlingException':
                sleep = sleep * 2   # Exponential backoff.
                if sleep > 5:
                    raise e
                print(f"Warning: Rate Limit fault while getting additional volumes. Sleeping for {sleep} seconds.")
                time.sleep(sleep)
            else:
                print(f"boto3 client error: {json.dumps(e.response)}")
                raise e

    return volumes

################################################################################
# This function will return all the alarms in the region. It will handle the
# case where there are more alarms than can be returned in a single call.
# It will also handle the case where we get a rate limit exception.
################################################################################
def getAlarms(cw):

    # The initial amount of time to sleep if there is a rate limit exception.
    sleep=.125
    while True:
        try:
            response = cw.describe_alarms()
            alarms = response['MetricAlarms']
            nextToken = response.get('NextToken', "")
            sleep=.125
            break
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'TooManyRequestsException' or e.response['Error']['Code'] == 'ThrottlingException':
                sleep = sleep * 2
                if sleep > 5:
                    raise e
                print(f"Warning: Rate Limit fault while getting the initial list of alarms. Sleeping for {sleep} seconds.")
                time.sleep(sleep)
            else:
                print(f"boto3 client error: {json.dumps(e.response)}")
                raise e

    while nextToken != "":
        try:
            response = cw.describe_alarms(NextToken=nextToken)
            alarms += response['MetricAlarms']
            nextToken = response.get('NextToken', "")
            sleep=.125
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'TooManyRequestsException' or e.response['Error']['Code'] == 'ThrottlingException':
                sleep = sleep * 2   # Exponential backoff.
                if sleep > 5:
                    raise e
                print(f"Warning: Rate Limit fault while getting additional alarms. Sleeping for {sleep} seconds.")
                time.sleep(sleep)
            else:
                print(f"boto3 client error: {json.dumps(e.response)}")
                raise e

    return alarms

################################################################################
# This is the main logic of the program. It loops on all the regions then all
# the fsx volumes within the region, checking to see if any of them already
# have a CloudWatch alarm, and if not, add one.
################################################################################
def lambda_handler(event, context):
    global customerId, regions, SNStopic, onlyFilesystemId
    #
    # Check for required parameters.
    if len(SNStopic) == 0:
        raise Exception("You must specify a SNS topic name to send the alarm messages to.")
    if len(accountId) == 0:
        raise Exception("You must specify the AWS account ID to use when creating the alarms.")
    #
    # If the customer ID is set, reformat it to be used in the alarm description.
    if customerId != '':
        customerId = f", CustomerID: {customerId}"
    #
    # Configure boto3 to use the more advanced "adaptive" retry method.
    boto3Config = Config(
        connect_timeout = 5,
        read_timeout = 30,
        retries = {
            'max_attempts': 2,
            'mode': 'adaptive'
        }
    )

    if len(regions) == 0:  # pylint: disable=E0601
        ec2Client = boto3.client('ec2', config=boto3Config)
        ec2Regions = ec2Client.describe_regions()['Regions']
        for region in ec2Regions:
            regions += [region['RegionName']]

    fsxRegions = boto3.Session().get_available_regions('fsx')
    for region in regions:
        if region in fsxRegions:
            print(f'Scanning {region}')
            try:
                fsxClient  = boto3.client('fsx', region_name=region, config=boto3Config)
                cwClient   = boto3.client('cloudwatch', region_name=region, config=boto3Config)
                tagsClient = boto3.client('resourcegroupstaggingapi', region_name=region, config=boto3Config)
                #
                # Get all the file systems, volumes, tags, and alarm in the region.
                fss = getFss(fsxClient) 
                if len(fss) == 0:
                    print('   No file systems found.')
                    continue
                volumes = getVolumes(fsxClient)
                alarms  = getAlarms(cwClient)
                tags    = getTags(tagsClient)
                #
                # Scan for filesystems without CPU Utilization Alarm.
                thresholds = {}
                for fs in fss:
                    if(fs['FileSystemType'] == "ONTAP"):
                        threshold = int(getAlarmThresholdTagValue(tags, fs['ResourceARN'], "cpu_alarm_threshold", defaultCPUThreshold))
                        fsId = fs['FileSystemId']
                        thresholds[fsId] = threshold
                        if(threshold != 100):
                            fsName = fsId.replace('fs-', 'FsxId')
                            alarmName = alarmPrefixCPU + fsId
                            alarmDescription = f"CPU utilization alarm for file system {fsName}{customerId} in region {region}."

                            if(not contains_alarm(alarmName, alarms) and onlyFilesystemId == None or
                               not contains_alarm(alarmName, alarms) and onlyFilesystemId != None and onlyFilesystemId == fsId):
                                print(f'Adding CPU alarm for {fs["FileSystemId"]}')
                                add_file_system_utilization_alarm(cwClient, fsId, "CPUUtilization", alarmName, alarmDescription, threshold, region)
                #
                # Scan for CPU alarms without a FSxN filesystem.
                for alarm in alarms:
                    alarmName = alarm['AlarmName']
                    if(alarmName[:len(alarmPrefixCPU)] == alarmPrefixCPU):
                        fsId = alarmName[len(alarmPrefixCPU):]
                        if(not contains_fs(fsId, fss) and onlyFilesystemId == None or
                           not contains_fs(fsId, fss) and onlyFilesystemId != None and onlyFilesystemId == fsId or
                           thresholds.get(fsId) == 100):
                            print("Deleting alarm: " + alarmName + " in region " + region)
                            delete_alarm(cwClient, alarmName)
                #
                # Scan for filesystems without disk throughput Utilization Alarm.
                thresholds = {}
                for fs in fss:
                    if(fs['FileSystemType'] == "ONTAP"):
                        threshold = int(getAlarmThresholdTagValue(tags, fs['ResourceARN'], "disk_throughput_alarm_threshold", defaultDiskThroughputThreshold))
                        fsId = fs['FileSystemId']
                        thresholds[fsId] = threshold
                        if(threshold != 100):
                            fsName = fsId.replace('fs-', 'FsxId')
                            alarmName = alarmPrefixDiskThroughput + fsId
                            alarmDescription = f"Disk throughput utilization alarm for file system {fsName}{customerId} in region {region}."

                            if(not contains_alarm(alarmName, alarms) and onlyFilesystemId == None or
                               not contains_alarm(alarmName, alarms) and onlyFilesystemId != None and onlyFilesystemId == fsId):
                                print(f'Adding disk throughput alarm for {fs["FileSystemId"]}')
                                add_file_system_utilization_alarm(cwClient, fsId, "FileServerDiskThroughputUtilization", alarmName, alarmDescription, threshold, region)
                #
                # Scan for disk throughput alarms without a FSxN filesystem.
                for alarm in alarms:
                    alarmName = alarm['AlarmName']
                    if(alarmName[:len(alarmPrefixDiskThroughput)] == alarmPrefixDiskThroughput):
                        fsId = alarmName[len(alarmPrefixDiskThroughput):]
                        if(not contains_fs(fsId, fss) and onlyFilesystemId == None or
                           not contains_fs(fsId, fss) and onlyFilesystemId != None and onlyFilesystemId == fsId or
                           thresholds.get(fsId) == 100):
                            print("Deleting alarm: " + alarmName + " in region " + region)
                            delete_alarm(cwClient, alarmName)
                #
                # Scan for filesystems without Network Throughput Utilization Alarm.
                thresholds = {}
                for fs in fss:
                    if(fs['FileSystemType'] == "ONTAP"):
                        threshold = int(getAlarmThresholdTagValue(tags, fs['ResourceARN'], "network_throughput_alarm_threshold", defaultNetworkThroughputThreshold))
                        fsId = fs['FileSystemId']
                        thresholds[fsId] = threshold
                        if(threshold != 100):
                            fsName = fsId.replace('fs-', 'FsxId')
                            alarmName = alarmPrefixNetworkThroughput + fsId
                            alarmDescription = f"Network throughput utilization alarm for file system {fsName}{customerId} in region {region}."

                            if(not contains_alarm(alarmName, alarms) and onlyFilesystemId == None or
                               not contains_alarm(alarmName, alarms) and onlyFilesystemId != None and onlyFilesystemId == fsId):
                                print(f'Adding network throughput alarm for {fs["FileSystemId"]}')
                                add_file_system_utilization_alarm(cwClient, fsId, "NetworkThroughputUtilization", alarmName, alarmDescription, threshold, region)
                #
                # Scan for Network Throughput alarms without a FSxN filesystem.
                for alarm in alarms:
                    alarmName = alarm['AlarmName']
                    if(alarmName[:len(alarmPrefixNetworkThroughput)] == alarmPrefixNetworkThroughput):
                        fsId = alarmName[len(alarmPrefixNetworkThroughput):]
                        if(not contains_fs(fsId, fss) and onlyFilesystemId == None or
                           not contains_fs(fsId, fss) and onlyFilesystemId != None and onlyFilesystemId == fsId or
                           thresholds.get(fsId) == 100):
                            print("Deleting alarm: " + alarmName + " in region " + region)
                            delete_alarm(cwClient, alarmName)
                #
                # Scan for filesystems without disk IOPS Utilization Alarm.
                thresholds = {}
                for fs in fss:
                    if(fs['FileSystemType'] == "ONTAP"):
                        threshold = int(getAlarmThresholdTagValue(tags, fs['ResourceARN'], "disk_iops_alarm_threshold", defaultDiskIOPSThreshold))
                        fsId = fs['FileSystemId']
                        thresholds[fsId] = threshold
                        if(threshold != 100):
                            fsName = fsId.replace('fs-', 'FsxId')
                            alarmName = alarmPrefixDiskIOPS + fsId
                            alarmDescription = f"Disk IOPS utilization alarm for file system {fsName}{customerId} in region {region}."

                            if(not contains_alarm(alarmName, alarms) and onlyFilesystemId == None or
                               not contains_alarm(alarmName, alarms) and onlyFilesystemId != None and onlyFilesystemId == fsId):
                                print(f'Adding disk IOPS Alarm for {fs["FileSystemId"]}')
                                add_file_system_utilization_alarm(cwClient, fsId, "FileServerDiskIopsUtilization", alarmName, alarmDescription, threshold, region)
                #
                # Scan for diks throughput alarms without a FSxN filesystem.
                for alarm in alarms:
                    alarmName = alarm['AlarmName']
                    if(alarmName[:len(alarmPrefixDiskIOPS)] == alarmPrefixDiskIOPS):
                        fsId = alarmName[len(alarmPrefixDiskIOPS):]
                        if(not contains_fs(fsId, fss) and onlyFilesystemId == None or
                           not contains_fs(fsId, fss) and onlyFilesystemId != None and onlyFilesystemId == fsId or
                           thresholds.get(fsId) == 100):
                            print("Deleting alarm: " + alarmName + " in region " + region)
                            delete_alarm(cwClient, alarmName)
                #
                # Scan for filesystems without SSD Utilization Alarm.
                thresholds = {}
                for fs in fss:
                    if(fs['FileSystemType'] == "ONTAP"):
                        fsId = fs['FileSystemId']
                        threshold = int(getAlarmThresholdTagValue(tags, fs['ResourceARN'], "ssd_alarm_threshold", defaultSSDThreshold))
                        thresholds[fsId] = threshold
                        if(threshold != 100):
                            fsName = fsId.replace('fs-', 'FsxId')
                            alarmName = alarmPrefixSSD + fsId
                            alarmDescription = f"SSD utilization alarm for file system {fsName}{customerId} in region {region}."

                            if(not contains_alarm(alarmName, alarms) and onlyFilesystemId == None or
                               not contains_alarm(alarmName, alarms) and onlyFilesystemId != None and onlyFilesystemId == fsId):
                                print(f'Adding SSD alarm for {fsId}')
                                add_ssd_alarm(cwClient, fs['FileSystemId'], alarmName, alarmDescription, threshold, region)
                #
                # Scan for SSD alarms without a FSxN filesystem.
                for alarm in alarms:
                    alarmName = alarm['AlarmName']
                    if(alarmName[:len(alarmPrefixSSD)] == alarmPrefixSSD):
                        fsId = alarmName[len(alarmPrefixSSD):]
                        if(not contains_fs(fsId, fss) and onlyFilesystemId == None or
                           not contains_fs(fsId, fss) and onlyFilesystemId != None and onlyFilesystemId == fsId or
                           thresholds.get(fsId) == 100):
                            print("Deleting alarm: " + alarmName + " in region " + region)
                            delete_alarm(cwClient, alarmName)
                #
                # Scan for volumes without alarms.
                thresholds = {}
                volumeFileThresholds = {}
                for volume in volumes:
                    if(volume['VolumeType'] == "ONTAP"):
                        volumeId = volume['VolumeId']
                        volumeName = volume['Name']
                        volumeARN = volume['ResourceARN']
                        fsId = volume['FileSystemId']

                        threshold = int(getAlarmThresholdTagValue(tags, volumeARN, "alarm_threshold", defaultVolumeThreshold))
                        thresholds[volumeId] = threshold
                        if(threshold != 100):   # No alarm if the value is set to 100.
                            alarmName = alarmPrefixVolume + volumeId
                            fsName = fsId.replace('fs-', 'FsxId')
                            alarmDescription = f"Volume utilization alarm for volumeId {volumeId}{customerId}, File System Name: {fsName}, Volume Name: {volumeName} in region {region}."
                            if(not contains_alarm(alarmName, alarms) and onlyFilesystemId == None or
                               not contains_alarm(alarmName, alarms) and onlyFilesystemId != None and onlyFilesystemId == fsId):
                                print(f'Adding volume utilization alarm for {volumeName} in region {region}.')
                                add_volume_alarm(cwClient, volumeId, alarmName, alarmDescription, fsId, threshold, region)

                        threshold = int(getAlarmThresholdTagValue(tags, volumeARN, "files_threshold", defaultVolumeFilesThreshold))
                        volumeFileThresholds[volumeId] = threshold
                        if(threshold != 100):   # No alarm if the value is set to 100.
                            alarmName = alarmFilesPrefixVolume + volumeId
                            fsName = fsId.replace('fs-', 'FsxId')
                            alarmDescription = f"Volume files utilization alarm for volumeId {volumeId}{customerId}, File System Name: {fsName}, Volume Name: {volumeName} in region {region}."
                            if(not contains_alarm(alarmName, alarms) and onlyFilesystemId == None or
                               not contains_alarm(alarmName, alarms) and onlyFilesystemId != None and onlyFilesystemId == fsId):
                                print(f'Adding volume files utilization alarm for {volumeName} in region {region}.')
                                add_volume_files_alarm(cwClient, volumeId, alarmName, alarmDescription, fsId, threshold, region)
                #
                # Scan for volume alarms without volumes.
                for alarm in alarms:
                    alarmName = alarm['AlarmName']
                    if alarmName[:len(alarmPrefixVolume)] == alarmPrefixVolume:
                        volumeId = alarmName[len(alarmPrefixVolume):]
                        if(not contains_volume(volumeId, volumes) and onlyFilesystemId == None or
                           not contains_volume(volumeId, volumes) and onlyFilesystemId != None and onlyFilesystemId == getFileSystemId(alarm) or
                           thresholds.get(volumeId) == 100):
                            print(f"Deleting alarm: {alarmName} in region {region}")
                            delete_alarm(cwClient, alarmName)

                    if alarmName[:len(alarmFilesPrefixVolume)] == alarmFilesPrefixVolume:
                        volumeId = alarmName[len(alarmFilesPrefixVolume):]
                        if(not contains_volume(volumeId, volumes) and onlyFilesystemId == None or
                           not contains_volume(volumeId, volumes) and onlyFilesystemId != None and onlyFilesystemId == getFileSystemId(alarm) or
                           volumeFileThresholds.get(volumeId) == 100):
                            print(f"Deleting alarm: {alarmName} in region {region}")
                            delete_alarm(cwClient, alarmName)

            except botocore.exceptions.ClientError as e:
                if e.response['Error']['Code'] == 'ServiceUnavailableException':
                    print(f"Warning: Service Unavailable fault while scanning {region}. Skipping")
                    continue
                else:
                    print(f"boto3 client error: {json.dumps(e.response)}")
                    raise e
            except botocore.exceptions.EndpointConnectionError as e:
                print(f"Warning: Endpoint Connection fault while scanning {region}. Skipping")
                continue
    return

################################################################################
# This function is used to print out the usage of the script.
################################################################################
def usage():
    print('Usage: auto_add_cw_alarms [-h|--help] [-d|--dryRun] [-c|--customerID customerID] [-a|--accountID aws_account_id] [-s|--SNStopic SNS_Topic] [-r|--region region] [-C|--CPUThreshold threshold] [-S|--SSDThreshold threshold] [-V|--VolumeThreshold threshold] [-F|--FilesThreshold threshold] [-N|--NetworkThroughputThreshold threshold] [-T|--DiskThroughputThreshold threshold] [-I|--DiskIOPSThreshold threshold]  [-f|--FileSystemID FileSystemID]')

################################################################################
# Main logic starts here.
################################################################################
#
# Set some default values.
regions = []
dryRun = False
#
# Check to see if there any any environment variables set.
customerId = os.environ.get('customerId', customerId)
accountId  = os.environ.get('accountId',  accountId)
SNStopic   = os.environ.get('SNStopic',   SNStopic)
onlyFilesystemId = None
defaultCPUThreshold                  = int(os.environ.get('defaultCPUThreshold',               defaultCPUThreshold))
defaultDiskThroughputThreshold       = int(os.environ.get('defaultDiskThroughputThreshold',    defaultDiskThroughputThreshold))
defaultNetworkThroughputThreshold    = int(os.environ.get('defaultNetworkThroughputThreshold', defaultNetworkThroughputThreshold))
defaultDiskIOPSThreshold             = int(os.environ.get('defaultDiskIOPSThreshold',          defaultDiskIOPSThreshold))
defaultSSDThreshold                  = int(os.environ.get('defaultSSDThreshold',               defaultSSDThreshold))
defaultVolumeThreshold               = int(os.environ.get('defaultVolumeThreshold',            defaultVolumeThreshold))
defaultVolumeFilesThreshold          = int(os.environ.get('defaultVolumeFilesThreshold',       defaultVolumeFilesThreshold))
regionsEnv = os.environ.get('regions', '')
if regionsEnv != '':
    regions = regionsEnv.split(',')
#
# Check to see if we are being run from a command line or a Lambda function.
if os.environ.get('AWS_LAMBDA_FUNCTION_NAME') == None:
    argumentList = sys.argv[1:]
    options = "hc:a:s:dr:C:S:V:f:F:T:N:I:"

    longOptions = ["help", "customerID=", "accountID=", "SNStopic=", "dryRun", "region=", "CPUThreshold=", "SSDThreshold=",\
                   "VolumeThreshold=", "FilesThreshold=", "FileSystemID=", "DiskThroughputThreshold=", "NetworkThroughputThreshold=",\
                   "DiskIOPSThreshold="]
    skip = False
    try:
        arguments, values = getopt.getopt(argumentList, options, longOptions)

        for currentArgument, currentValue in arguments:
            if currentArgument in ("-h", "--help"):
                usage()
                skip = True
            elif currentArgument in ("-c", "--customerID"):
                customerId = currentValue
            elif currentArgument in ("-a", "--accountID"):
                accountId = currentValue
            elif currentArgument in ("-s", "--SNStopic"):
                SNStopic = currentValue
            elif currentArgument in ("-C", "--CPUThreshold"):
                defaultCPUThreshold = int(currentValue)
            elif currentArgument in ("-N", "--NetworkThroughputThreshold"):
                defaultNetworkThroughputThreshold = int(currentValue)
            elif currentArgument in ("-T", "--DiskThroughputThreshold"):
                defaultDiskThroughputThreshold = int(currentValue)
            elif currentArgument in ("-I", "--DiskIOPSThreshold"):
                defaultDiskIOPSThreshold = int(currentValue)
            elif currentArgument in ("-S", "--SSDThreshold"):
                defaultSSDThreshold = int(currentValue)
            elif currentArgument in ("-V", "--VolumeThreshold"):
                defaultVolumeThreshold = int(currentValue)
            elif currentArgument in ("-F", "--FilesThreshold"):
                defaultVolumeFilesThreshold = int(currentValue)
            elif currentArgument in ("-d", "--dryRun"):
                dryRun = True
            elif currentArgument in ("-r", "--region"):
                regions += [currentValue]
            elif currentArgument in ("-f", "--FileSystemID"):
                onlyFilesystemId = currentValue

    except getopt.error as err:
        print(str(err))
        usage()
        skip = True

    if not skip:
        lambda_handler(None, None)
