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
    # Take a sneak peek at the snsTopicArn environment variable so messages can be sent
    # to it if any of the other enviornment variables are missing.
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
    for var in ['s3BucketName', 's3BucketRegion', 'FSxNList', 'MOSLambdaFunctionName', 'snsTopicArn']:
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
    # Invoke the monitoring Lambda function for each FSxN in the list.
    lambda_client = boto3.client('lambda')
    lineNum = 0
    for fsxn in FSxNList:
        lineNum += 1
        parts = [x.strip() for x in fsxn.split(',')]
        #
        # Skip comments, empty and invalid lines.
        if parts[0][0:1] == "#" or parts[0][0:1] == "":
            continue
        if len(parts) < 2:
            logger.warning(f"Skipping invalid fsxn entry on line {lineNum}.")
            continue

        OntapAdminServer = parts[0]
        payload['OntapAdminServer'] = OntapAdminServer
        payload['secretArn'] = parts[1]

        for param in parts[2:]:
            try:
                key, value = param.split('=')
                payload[key.strip()] = value.strip()
            except ValueError:
                logger.warning(f"Skipping invalid parameter '{param}' for {OntapAdminServer} on line {lineNum}. No '=' found.")
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
                InvocationType='Event',
                Payload=json.dumps(payload)
            )
            logger.info(f"Invoked Monitoring Lambda function for {OntapAdminServer}.")
        except botocore.exceptions.ClientError as e:
            snsClient.publish(TopicArn=snsTopicArn, Subject="MOS Controller Error: Failed to invoke monitoring function", Message=e)
            logger.error(f"Error invoking Monitoring Lambda function for {OntapAdminServer}: {e}")

if os.environ.get('AWS_LAMBDA_FUNCTION_NAME') is None:
    lambda_handler({}, {})
# END CONTROLLER CODE. DO NOT DELETE THIS LINE.
