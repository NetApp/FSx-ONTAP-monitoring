#!/bin/python3
#
# This script is used to delete all the alarms that the auto_add_cw_alarms.py
# script created with the option to only delete the ones that have been in
# alarm state for the specified number of hours.
################################################################################
import boto3
import botocore
import os
import sys
import datetime
import getopt

################################################################################
# This function is used to delete all the alarms in the specified region that
# the auto_add_cw_alarms.py script created, based on the basePrefix, that
# optionally have been in the ALARM state for more than alarmAge hours.
################################################################################
def delete_all_alarms(region):
    global basePrefix, dryRun, alarmAge
    #
    # Create a CloudWatch client
    cloudwatchClient = boto3.client('cloudwatch', region_name=region, config=boto3Config)
    #
    # Get all alarms
    try:
        response = cloudwatchClient.describe_alarms(AlarmNamePrefix=basePrefix)
        alarms = response['MetricAlarms']
        while 'NextToken' in response:
            nextToken = response['NextToken']
            response = cloudwatchClient.describe_alarms(AlarmNamePrefix=basePrefix, NextToken=nextToken)
            alarms += response['MetricAlarms']
    #
    # These are the exceptions that have been observed being thrown when a region is offline.
    except (botocore.exceptions.ReadTimeoutError, botocore.exceptions.ConnectTimeoutError, botocore.exceptions.ConnectionClosedError) as e:
        print(f"Warning: boto3 client error while getting the list of alarms. Exception: {e}. Skipping...")
        return
    #
    # Get the current time in UTC
    currentTime = datetime.datetime.now(datetime.timezone.utc)
    #
    # Check to see which alarms to delete.
    for alarm in alarms:
        alarmName = alarm['AlarmName']
        if alarmAge is not None:
            if alarm['StateValue'] == 'ALARM' and alarm['StateTransitionedTimestamp'] < (currentTime - datetime.timedelta(hours=alarmAge)):
                if dryRun:
                    print(f"Would have deleted alarm: {alarmName}.")
                else:
                    print(f"Deleting alarm: {alarmName}.")
                    cloudwatchClient.delete_alarms(AlarmNames=[alarmName])
        else:
            if dryRun:
                print(f"Would have deleted alarm: {alarmName}.")
            else:
                print(f"Deleting alarm: {alarmName}.")
                cloudwatchClient.delete_alarms(AlarmNames=[alarmName])

    cloudwatchClient.close()

################################################################################
################################################################################
def lambda_handler(event, context):
    global regions

    if len(regions) == 0:  # pylint: disable=E0601
        ec2Client = boto3.client('ec2')
        ec2Regions = ec2Client.describe_regions()['Regions']
        for region in ec2Regions:
            regions += [region['RegionName']]

    fsxRegions = boto3.Session().get_available_regions('fsx')
    for region in regions:
        if region in fsxRegions:
            print(f'Processing {region}')
            delete_all_alarms(region)

################################################################################
# This function is used to print out the usage of the script.
################################################################################
def usage():
    print('Usage: delete_alarms [-h|--help] [-d|--dryRun] [-r|--regions <region>[,region>...]] [-a|--alarmAge <hours>] [-b |--basePrefix <prefix>]')
    print('  -h, --help: Show this help message and exit.')
    print('  -d, --dryRun: Show what alarms would be deleted without actually deleting them.')
    print('  -r, --region regions: a comma separated list of regions to process.')
    print('  -a, --alarmAge: Only delete alarms that are in the ALARM state and have been in that state for more than <hours>.')
    print('  -b, --basePrefix: The prefix the alarm name must start with to be considered. Default is FSx-ONTAP-Auto.')

################################################################################
# Main logic starts here.
################################################################################
#
# Set some default values.
basePrefix = os.environ.get('basePrefix', "FSx-ONTAP-Auto")

regions = []
regionsEnv = os.environ.get('regions', '')
if regionsEnv != '':
    regions = regionsEnv.split(',')

dryRun = os.environ.get('dryRun', "")
if dryRun.lower() == "true":
    dryRun = True
else:
    dryRun = False

alarmAge = os.environ.get('alarmAge', "")
if alarmAge != "":
    alarmAge = int(alarmAge)
else:
    alarmAge = None
#
# Configure boto3 to not wait so long for a response from the AWS API.
boto3Config = botocore.config.Config(
    connect_timeout = 5,
    read_timeout = 30,
    retries = {
        'max_attempts': 2,
    }
)
#
# If were being called from the command line, parse the arguments, and call the lambda_handler function.
if os.environ.get('AWS_LAMBDA_FUNCTION_NAME') == None:
    argumentList = sys.argv[1:]
    options = "hda:r:b:"

    longOptions = ["help", "dryRun", "alarmAge=", "regions=", "basePrefix="]
    skip = False
    try:
        arguments, values = getopt.getopt(argumentList, options, longOptions)

        for currentArgument, currentValue in arguments:
            if currentArgument in ("-h", "--help"):
                usage()
                skip = True
            elif currentArgument in ("-d", "--dryRun"):
                dryRun = True
            elif currentArgument in ("-r", "--regions"):
                regions = currentValue.split(",")
            elif currentArgument in ("-a", "--alarmAge"):
                alarmAge = int(currentValue)
            elif currentArgument in ("-b", "--basePrefix"):
                basePrefix = currentValue

    except getopt.error as err:
        print(str(err))
        usage()
        skip = True

    if not skip:
        lambda_handler(None, None)
