#!/usr/bin/env python3
# BEGIN CONTROLLER CODE. DO NOT DELETE THIS LINE.
#
# This function is used to trigger the monitoring function with the appropriate
# parameters. It reads in a list of FSxNs to monitor from the S3 bucket and
# invokes the monitoring Lambda function for each one of them.
#
# The format of the FSxN list file is as follows:
# hostname,secret_ARN,parameter=value,...
#
# Where parameter is any of the optional configuration parameters supported by
# the monitoring function.
#
# Blank lines and lines starting with a '#' are ignored allowing you to add
# comments or disable a system without having to delete the entry.
################################################################################

import json
import boto3
import botocore
import os
import logging

def lambda_handler(event, context):
    #
    # Maximum number of allowed consecutive failed invokes before sending an alert.
    maxAllowedFailures = 2

    logging.basicConfig()
    logger = logging.getLogger("MOS_Controller")
    logger.setLevel(logging.DEBUG)
    #
    # Take a sneak peek at the snsTopicArn so messages can be sent if any of the other
    # enviornment variables are missing.
    snsClient = None
    if os.environ.get('snsTopicArn') is not None:
        snsTopicArn = os.environ.get('snsTopicArn')
        snsRegion = snsTopicArn.split(':')[3]
        snsClient = boto3.client('sns', region_name=snsRegion)
    #
    # Check for required environment variables and store them in the payload variable.
    # Don't really need to send some of these to the monitoring function, but it
    # doesn't hurt to do so.
    payload = {}
    for var in ['s3BucketName', 's3BucketRegion', 'FSxNList', 'MOSLambdaFunctionName', 'snsTopicArn', 'monitorInvocationType', 'FSxNStatusFilename']:
        if os.environ.get(var) is None:
            err = f"Error, the Monitor ONTAP Service controller is missing a required environment variable {var}."
            logger.error(err)
            if snsClient is not None:
                snsClient.publish(TopicArn=snsTopicArn, Subject="MOS Controller Error", Message=err)
            raise Exception(err)  # This is a crtical error, so send up a flare.
        else:
            payload[var] = os.environ[var]
    #
    # Read the FSxN list from S3.
    s3Client = boto3.client('s3', region_name=payload['s3BucketRegion'])
    try:
        response = s3Client.get_object(Bucket=payload['s3BucketName'], Key=payload['FSxNList'])
        FSxNListContent = response['Body'].read().decode('utf-8')
        FSxNList = FSxNListContent.split('\n')
    except botocore.exceptions.ClientError as e:
        err = f"Error, the Monitor ONTAP Service controller was unable to fetching FSxN list from S3: {e}"
        logger.error(err)
        snsClient.publish(TopicArn=snsTopicArn, Subject="MOS Controller Error", Message=err)
        raise Exception(err)  # This is a crtical error, so send up a flare.
    #
    # Get the previous status.
    changedEvents = False
    try:
        data = s3Client.get_object(Key=payload['FSxNStatusFilename'], Bucket=payload["s3BucketName"])
    except botocore.exceptions.ClientError as err:
        # If the error is that the object doesn't exist, then this must be the
        # first time this script has run against thie filesystem so create an
        # initial status structure.
        if err.response['Error']['Code'] == "NoSuchKey":
            FSxNStatus = {}
            changedEvents = True
        else:
            raise Exception(f"Error, the Monitor of ONTAP Services controller could not retrieve the previous state of the FSxNs object '{payload['FSxNStatusFilename']} from S3 bucket {payload['s3BucketName']}: {err}")
    else:
        FSxNStatus = json.loads(data['Body'].read().decode('utf-8'))

    lambda_client = boto3.client('lambda')
    lineNum = 0
    for fsxn in FSxNList:
        lineNum += 1
        parts = [x.strip() for x in fsxn.split(',')]
        #
        # Skip comments, empty and invalid lines.
        if parts[0][0:1] == "#" or parts[0][0:1] == "":
            continue
        if len(parts) < 3:
            logger.warning(f"Skipping invalid fsxn entry on line {lineNum}.")
            continue

        OntapAdminServer = parts[0]
        payload['OntapAdminServer'] = OntapAdminServer
        payload['secretArn'] = parts[1]

        for param in parts[2:]:
            key, value = param.split('=')
            payload[key.strip()] = value.strip()
        #
        # Include all the "initial" variables in case the Lambda function has to create an initial conditions file.
        for key, value in os.environ.items():
            if key.startswith('initial'):
                payload[key] = value
        #
        # Invoke the MOS Lambda function.
        try:
            response = lambda_client.invoke(
                FunctionName=payload['MOSLambdaFunctionName'],
                InvocationType='Event' if payload['monitorInvocationType'].lower() == 'asynchronous' else 'RequestResponse',
                Payload=json.dumps(payload)
            )
            if response.get('FunctionError') is None:
                logger.info(f"Invoked MOS Lambda for {OntapAdminServer} was successful.")
                if FSxNStatus.get(OntapAdminServer) is None:
                    FSxNStatus[OntapAdminServer] = {'NumberOfFailedInvokes': 0}
                    changedEvents = True
                else:
                    if FSxNStatus[OntapAdminServer]['NumberOfFailedInvokes'] != 0:
                        FSxNStatus[OntapAdminServer]['NumberOfFailedInvokes'] = 0
                        changedEvents = True
            else:
                err = f"The monitoring function failed while processing {OntapAdminServer}: {response['Payload'].read().decode('utf-8')}"
                logger.error(err)
                if FSxNStatus.get(OntapAdminServer) is None:
                    FSxNStatus[OntapAdminServer] = {'NumberOfFailedInvokes': 1}
                    changedEvents = True
                else:
                    if (FSxNStatus[OntapAdminServer].get('NumberOfFailedInvokes')+1) == maxAllowedFailures:
                        FSxNStatus[OntapAdminServer]['NumberOfFailedInvokes'] += 1
                        changedEvents = True
                        snsClient.publish(TopicArn=snsTopicArn, Subject="MOS Controller Error", Message=err)
                    elif FSxNStatus[OntapAdminServer]['NumberOfFailedInvokes'] < maxAllowedFailures:
                        FSxNStatus[OntapAdminServer]['NumberOfFailedInvokes'] += 1
                        changedEvents = True
        except botocore.exceptions.ClientError as e:
            snsClient.publish(TopicArn=snsTopicArn, Subject="MOS Controller Error", Message=err)
            logger.error(f"Error invoking MOS Monitoring Lambda function for {OntapAdminServer}: {e}")

    if changedEvents:
        #
        # Write the updated status back to S3.
        s3Client.put_object( Bucket=payload['s3BucketName'], Key=payload['FSxNStatusFilename'], Body=json.dumps(FSxNStatus).encode('utf-8'))

if os.environ.get('AWS_LAMBDA_FUNCTION_NAME') is None:
    lambda_handler({}, {})
# END CONTROLLER CODE. DO NOT DELETE THIS LINE.
