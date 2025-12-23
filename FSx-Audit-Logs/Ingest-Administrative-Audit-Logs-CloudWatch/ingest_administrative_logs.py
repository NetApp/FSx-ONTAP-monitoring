#!/bin/python3
#
################################################################################
# This script is used to ingest all the administrative audit logs events
# from all the FSx for ONTAP File Systems.
#
# It will create a log stream for each FSxN file system it finds.
# It will attempt to process every FSxN file system within the specified
# regions. If the regions variable is empty, it will process all regions.
# It leverages AWS secrets manager to get the credentials for the user account
# to use for each FSxN file systems.
# It will skip any FSxN file system that it doesn't have credentials for.
# It will maintain a file in the specified S3 bucket that has the last
# processed event for each FSxN so that it will not duplicate events.
#
################################################################################
#
import urllib3
import re
import datetime
import os
import json
import logging
from urllib3.util import Retry
import boto3
import botocore
from botocore.config import Config as BotoConfig

################################################################################
# You can configure this script by either setting the following variables in
# code below, by uncommenting them, or by setting environment variables with
# the same name. One exception to this is with the secretARNs variable. It only
# can only be set in the code below.
################################################################################
#
# There are 4 ways to specify secrets for your FSxNs:
# 1. Set the secretARNs variable to a dictionary that contains the
#    secret ARNs for the FSxNs you want to process.
# 2. Set the fsxnSecretARNsFile variable to the name of a file in the S3
#    bucket that contains the secret ARNs for the FSxN file systems.
# 3. Set the fileSystem1ID, fileSystem2ID, fileSystem3ID, fileSystem4ID,
#    and fileSystem5ID variables to the fsId of the FSxN file systems. Then set
#    the fileSystem1SecretARN, fileSystem2SecretARN, fileSystem3SecretARN,
#    fileSystem4SecretARN, and fileSystem5SecretARN variables to the
#    secretARNs for the FSxN file systems.
# 4. Set the defaultSecretARN variable to the secret ARN of the secret that
#    This will be used if FSxN file system does not have a specific
#    secret ARN specified.
#
# *NOTE*: Each secret should have two keys: 'username' and 'password' set to
# the appropriate values.
#
################################################################################
#
# Variable: secretARNs
#
# The secretARNs variable contains the secretARNs for all the FSxNs you want
# to process. Unlike the rest of the variables, this one cannot be set via an
# environment variable. There are three options to populate the secretsARN
# dictionary:
#
# Create the 'secretARNs' variable by un-commenting out the code segment
# below that defines dictionary with the following structure:
#
# secretARNs =  {
#     "<fsId-1>": "<secretARN>",
#     "<fsId-2>": "<secretARN>",
#     "<fsId-3>": "<secretARN>"
#   }
#
################################################################################
#
# Variable: fsxnSecretARNsFile
#
# Set the fsxnSecretARNsFile variable to the name of a file in the S3
# bucket that contains the secretARNs.
#
# fsxnSecretARNsFile=
#
# The format of that file should be:
#
# <fsId-1>=<secretARN>
# <fsId-2>=<secretARN>
#
################################################################################
#
# Variables: fileSystem1ID, fileSystem2ID, fileSystem3ID, fileSystem4ID,
# fileSystem5ID, fileSystem1SecretARN, fileSystem2SecretARN,
# fileSystem3SecretARN, fileSystem4SecretARN
#
# Set the fileSystem1ID, fileSystem2ID, fileSystem3ID, fileSystem4ID, and
# fileSystem5ID variables to the fsIds of the FSxN file systems. Then set
# the fileSystem1SecretARN, fileSystem2SecretARN, fileSystem3SecretARN,
# fileSystem4SecretARN, and fileSystem5SecretARN variables to the
# secretARNs for the FSxN file systems. Empty, or variables not defined
# will be ignored.
#
# *NOTE*: If fsxnSecretARNsFile is set, then these variables will be ignored.
#
# fileSystem1ID =
# fileSystem1SecretARN =
# fileSystem2ID =
# fileSystem2SecretARN =
# fileSystem3ID =
# fileSystem3SecretARN =
# fileSystem4ID =
# fileSystem4SecretARN =
# fileSystem5ID =
# fileSystem5SecretARN =
#
################################################################################
#
# Variable: defaultSecretARN
#
# The defaultSecretARN variable contains the secretARN of the secret that
# contains the credentials for the FSxN file systems. This will be used
# if a specific FSxN file system does not have a secretARN specified.
# Use with caution, since it will cause the prograrm to try the credentials
# in the default secret for all FSxN where there isn't a secret specified
# which could cause an account to be locked out if the credentials are
# incorrect for that FSxN.
#
# defaultSecretARN =
#
################################################################################
#
# Variables: s3BucketRegion & s3BucketName
#
# Specify what S3 bucket to use to store the last stored event and potentially
# the secretsARNs file.
#
# s3BucketRegion = "us-west-2"
# s3BucketName = ""
#
################################################################################
#
# Variable: statsName
#
# The name of the "last processed event" file.
# statsName = "lastFileRead"
#
################################################################################
#
# Variables: logGroupRegion, logGroupName
#
# Define the name of the CloudWatch log group, and its region, where the
# administrative events will be stored into.
#
# *NOTE*: It must already exist.
#
# logGroupRegion = "us-west-2"
# logGroupName = "/fsx/audit_logs"
#
################################################################################
#
# Variable: inputFilter
#
# The inputFiler is a regular expression that is used to filter out
# the audit log events based on the 'input' field of the event. If the
# inputFilter is set, then the event will be skipped if the 'input' field
# matches the inputFilter. If the inputFilter is not set, then all events
# will be stored.
#
# inputFilter=""
#
################################################################################
#
# Variable: inputMatch
#
# The inputMatch is a regular expression that is used to match the 'input'
# field of the event. If the inputMatch is set, then ONLY the events that
# the 'input' field matches the inputMatch will be stored. If the inputMatch
# is not set, then all events will be recorded.
#
# inputMatch=""
#
################################################################################
#
# Variables: applicationMatch, userMatch, stateMatch
#
# These are regular expressions that are used to match the 'application',
# 'user', and 'state' fields of the event. If these are set, then ONLY events
# that match the 'application', 'user', and 'state' fields will be stored.
# If these are not set, then all events will be recorded.
#
# applicationMatch=""
# userMatch=""
# stateMatch=""
#
################################################################################
#
# Variable: regions
#
# This is an array of AWS regions that you want the program to search for
# FSxNs in. If it is left empty, it will search all regions that support
# FSx for ONTAP. For example:
# regions = ["us-west-2", "us-east-1", "eu-west-1"]
regions = []
#
################################################################################
#
# Variable: accountRoles
#
# This is an array of AWS account roles that you want the program to assume
# before searching for FSxNs in. If it is left empty, it only searches the
# current account.
#
# The only permission required in the role is "fsx:DescribeFileSystems".
#
accountRoles = []
#
################################################################################
#
# Variable: scanCurrentAccount
#
# This controls whether the program will look at the current account for
# FSxN to process. Set to the string 'no' to keep it from scanning the
# current account. Any other value, including not setting the variable
# or setting it to a null string, will result in it scanning the current
# account.
#
# scanCurrentAccount=""
#
################################################################################
# END OF VARIABLE DEFINITIONS
################################################################################

################################################################################
# This function returns the millisecond since January 1st 1970 (epoch time)
# from a date string. The format of the string is expected to be:
#     2025-07-14T08:08:48-06:00
#     YYYY-MM-DDTHH:MM:SS±HH:MM
#
################################################################################
def getMsEpoch(dateStr):
    ymdStr = dateStr.split('T')[0]
    timeStr = dateStr.split('T')[1][0:8]

    year = int(ymdStr.split('-')[0])
    month = int(ymdStr.split('-')[1])
    day = int(ymdStr.split('-')[2])

    hour = int(timeStr.split(':')[0])
    minute = int(timeStr.split(':')[1])
    second = int(timeStr.split(':')[2])

    msEpoch = int(datetime.datetime(year, month, day, hour, minute, second, 0, datetime.timezone.utc).timestamp()*1000)

    offset = int(dateStr.split(':')[2][3:5])
    if dateStr.split(':')[2][2] == '-':
        msEpoch += int(offset*60*60*1000)  # Convert offset to milliseconds and subtract it
    else:
        msEpoch -= int(offset*60*60*1000)  # Convert offset to milliseconds and add it
    return msEpoch

################################################################################
# This puts the CloudWatch events into the CloudWatch log stream.
################################################################################
def putEventInCloudWatch(cwEvents, logStreamName):
    global cwLogsClient, config, logger
    #
    # Ensure the logstream exists.
    try:
        cwLogsClient.create_log_stream(logGroupName=config['logGroupName'], logStreamName=logStreamName)
    except cwLogsClient.exceptions.ResourceAlreadyExistsException:
        pass

    logger.debug(f"Putting {len(cwEvents)} events into CloudWatch")
    response = cwLogsClient.put_log_events(logGroupName=config['logGroupName'], logStreamName=logStreamName, logEvents=cwEvents)
    if response.get('rejectedLogEventsInfo') != None:
        if response['rejectedLogEventsInfo'].get('tooNewLogEventStartIndex') is not None:
            logger.warning(f"Too new log event start index: {response['rejectedLogEventsInfo']['tooNewLogEventStartIndex']}")
        if response['rejectedLogEventsInfo'].get('tooOldLogEventEndIndex') is not None:
            logger.warning(f"Too old log event end index: {response['rejectedLogEventsInfo']['tooOldLogEventEndIndex']}")

################################################################################
# This function scans for FSxNs and populates the fsxNs global variable
# with the name and the IP address of the FSxNs management ports.
################################################################################
def scanFsxNs(fsxClient):
    global fsxNs, logger
    #
    # Get a list of FSxNs in the region.
    logger.debug("Getting FSxNs")
    fsxResponse = fsxClient.describe_file_systems()
    for fsx in fsxResponse['FileSystems']:
        try:
            fsxNs.append({"name": fsx['FileSystemId'], "IP": fsx['OntapConfiguration']['Endpoints']['Management']['IpAddresses'][0]})
        except KeyError: # Skip any that don't have their IP address assigned yet.
            pass
    #
    # Make sure to get all of them since the response is paginated.
    while fsxResponse.get('NextToken') is not None:
        logger.debug("Getting more FSxNs")
        fsxResponse = fsxClient.describe_file_systems(NextToken=fsxResponse['NextToken'])
        for fsx in fsxResponse['FileSystems']:
            try:
                fsxNs.append({"name": fsx['FileSystemId'], "IP": fsx['OntapConfiguration']['Endpoints']['Management']['IpAddresses'][0]})
            except KeyError: # Skip any that don't have their IP address assigned yet.
                pass

################################################################################
# This function checks that all the required configuration variables are set.
# And in the process, builds the "config" dictionary that contains all the
# configuration variables.
################################################################################
def checkConfig():
    global config, s3Client, secretARNs, regions, boto3Config, logger
    #
    # When defining the dictionary, initialize them to any variables that are set at the top of the program.
    config = {
        'logGroupName': logGroupName if 'logGroupName' in globals() else None,                    # pylint: disable=E0602
        'logGroupRegion': logGroupRegion if 'logGroupRegion' in globals() else None,              # pylint: disable=E0602
        'regions': regions if 'regions' in globals() else [],                                     # pylint: disable=E0602
        'accountRoles': accountRoles if 'accountRoles' in globals() else [],                      # pylint: disable=E0602
        'scanCurrentAccount': scanCurrentAccount if 'scanCurrentAccount' in globals() else None,  # pylint: disable=E0602
        's3BucketRegion': s3BucketRegion if 's3BucketRegion' in globals() else None,              # pylint: disable=E0602
        's3BucketName': s3BucketName if 's3BucketName' in globals() else None,                    # pylint: disable=E0602
        'statsName': statsName if 'statsName' in globals() else None,                             # pylint: disable=E0602
        'inputFilter': inputFilter if 'inputFilter' in globals() else None,                       # pylint: disable=E0602
        'inputMatch': inputMatch if 'inputMatch' in globals() else None,                          # pylint: disable=E0602
        'applicationMatch': applicationMatch if 'applicationMatch' in globals() else None,        # pylint: disable=E0602
        'userMatch': userMatch if 'userMatch' in globals() else None,                             # pylint: disable=E0602
        'stateMatch': stateMatch if 'stateMatch' in globals() else None,                          # pylint: disable=E0602
        'fsxnSecretARNsFile': fsxnSecretARNsFile if 'fsxnSecretARNsFile' in globals() else None,  # pylint: disable=E0602
        'defaultSecretARN': defaultSecretARN if 'defaultSecretARN' in globals() else None,        # pylint: disable=E0602
        'fileSystem1ID': fileSystem1ID if 'fileSystem1ID' in globals() else None,                 # pylint: disable=E0602
        'fileSystem2ID': fileSystem2ID if 'fileSystem2ID' in globals() else None,                 # pylint: disable=E0602
        'fileSystem3ID': fileSystem3ID if 'fileSystem3ID' in globals() else None,                 # pylint: disable=E0602
        'fileSystem4ID': fileSystem4ID if 'fileSystem4ID' in globals() else None,                 # pylint: disable=E0602
        'fileSystem5ID': fileSystem5ID if 'fileSystem5ID' in globals() else None,                 # pylint: disable=E0602
        'fileSystem1SecretARN': fileSystem1SecretARN if 'fileSystem1SecretARN' in globals() else None,  # pylint: disable=E0602
        'fileSystem2SecretARN': fileSystem2SecretARN if 'fileSystem2SecretARN' in globals() else None,  # pylint: disable=E0602
        'fileSystem3SecretARN': fileSystem3SecretARN if 'fileSystem3SecretARN' in globals() else None,  # pylint: disable=E0602
        'fileSystem4SecretARN': fileSystem4SecretARN if 'fileSystem4SecretARN' in globals() else None,  # pylint: disable=E0602
        'fileSystem5SecretARN': fileSystem5SecretARN if 'fileSystem5SecretARN' in globals() else None   # pylint: disable=E0602
    }
    optionalConfig = ['fsxnSecretARNsFile', 'inputFilter', 'inputMatch', 'applicationMatch', 'userMatch', 'stateMatch',
                      'fileSystem1ID', 'fileSystem2ID', 'fileSystem3ID', 'fileSystem4ID', 'regions', 'accountRoles',
                      'fileSystem5ID', 'fileSystem1SecretARN', 'fileSystem2SecretARN', 'defaultSecretARN', 'scanCurrentAccount',
                      'fileSystem3SecretARN', 'fileSystem4SecretARN', 'fileSystem5SecretARN']
    #
    # Check to see if any variables are set via environment variables.
    for item in config.copy():
        if item == "accountRoles":
            if len(config[item]) == 0 and os.environ.get(item) is not None and os.environ[item] != '':
                config[item] = os.environ[item].split(',')
                for i in range(len(config[item])):
                    config[item][i] = config[item][i].strip()
        elif item == "regions":
            if len(config[item]) == 0 and os.environ.get(item) is not None and os.environ[item] != '':
                config[item] = os.environ[item].split(',')
                for i in range(len(config[item])):
                    config[item][i] = config[item][i].strip()
        else:
            if config[item] is None:
                config[item] = os.environ.get(item)
                #
                # Since CloudFormation will create environment variables for everything, but set them to an
                # empty string if the variable wasn't set, set the configuration variable back to None.
                if config[item] == "":
                    config[item] = None
    #
    # To be backwards compatible, if the fsxRegion environment variable is set,
    # and logGroupRegion and/or regions is not set, then set them to the fsxRegion.
    if os.environ.get('fsxRegion') is not None and os.environ['fsxRegion'] != '':
        if config['logGroupRegion'] is None:
            config['logGroupRegion'] = os.environ['fsxRegion']
        if len(config['regions']) == 0:
            config['regions'] = [os.environ['fsxRegion']]
    #
    # Check that all the required variables are set.
    for item in config:
        if item not in optionalConfig and config[item] is None:
            raise Exception(f"{item} is not set.")
    #
    # Create a S3 client.
    s3Client = boto3.client('s3', region_name=config['s3BucketRegion'], config=boto3Config)
    #
    # Define the secretsARNs dictionary if it hasn't already been defined.
    if 'secretARNs' not in globals():
        secretARNs = {}
        #
        # If the fsxnSecretARNsFile is set, then read the file from S3 and populate the secretARNs dictionary.
        if config['fsxnSecretARNsFile'] is not None and config['fsxnSecretARNsFile'] != '':
            try:
                response = s3Client.get_object(Bucket=config['s3BucketName'], Key=config['fsxnSecretARNsFile'])
            except botocore.exceptions.ClientError as err:
                raise Exception(f"Unable to open parameter file with secrets '{config['fsxnSecretARNsFile']}' from S3 bucket '{config['s3BucketName']}': {err}")
            else:
                for line in response['Body'].iter_lines():
                    line = line.decode('utf-8')
                    line = line.strip()
                    if line.startswith('#'):
                        continue
                    if line == '':
                        continue
                    fsId, secretArn = line.split('=')
                    secretARNs[fsId.strip()] = secretArn.strip()
        else:
            if config['fileSystem1ID'] is not None and config['fileSystem1SecretARN'] is not None:
                secretARNs[config['fileSystem1ID']] = config['fileSystem1SecretARN']
            if config['fileSystem2ID'] is not None and config['fileSystem2SecretARN'] is not None:
                secretARNs[config['fileSystem2ID']] = config['fileSystem2SecretARN']
            if config['fileSystem3ID'] is not None and config['fileSystem3SecretARN'] is not None:
                secretARNs[config['fileSystem3ID']] = config['fileSystem3SecretARN']
            if config['fileSystem4ID'] is not None and config['fileSystem4SecretARN'] is not None:
                secretARNs[config['fileSystem4ID']] = config['fileSystem4SecretARN']
            if config['fileSystem5ID'] is not None and config['fileSystem5SecretARN'] is not None:
                secretARNs[config['fileSystem5ID']] = config['fileSystem5SecretARN']

    if len(secretARNs) == 0 and config['defaultSecretARN'] is None:
        raise Exception("No secretARNs were specified.")
    #
    # Since regular expressions can't be None, we need to set them to empty strings.
    for matchVar in 'inputFilter', 'inputMatch', 'applicationMatch', 'userMatch', 'stateMatch':
        if config[matchVar] is None:
            config[matchVar] = ""

################################################################################
# This is the main function that checks that everything is configured correctly
# and then processes all the FSxNs.
################################################################################
def lambda_handler(event, context):     # pylint: disable=W0613
    global http, cwLogsClient, config, s3Client, secretARNs, fsxNs, logger, lambdaFunction, boto3Config
    #
    # Set up logging.
    logging.basicConfig()
    logger = logging.getLogger("ingest_admin_logs")
    if lambdaFunction:
        logger.setLevel(logging.INFO)       # Anything at this level and above this gets logged.
    else: # Assume we are running in a test environment.
        logger.setLevel(logging.DEBUG)      # Anything at this level and above this gets logged.
        formatter = logging.Formatter(
                fmt="%(name)s:%(funcName)s - Level:%(levelname)s - Message:%(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
        loggerscreen = logging.StreamHandler()
        loggerscreen.setFormatter(formatter)
        logger.addHandler(loggerscreen)

    boto3Config = BotoConfig(
        connect_timeout=10,
        read_timeout=10,
        retries={'mode': 'adaptive', 'total_max_attempts': 3}
    )
    #
    # Check that we have all the configuration variables we need.
    checkConfig()
    #
    # NOTE: The s3 client is created in the checkConfig function.
    #
    # Create a CloudWatch client.
    cwLogsClient = boto3.client('logs', region_name=config['logGroupRegion'], config=boto3Config)
    #
    # Disable warning about connecting to servers with self-signed SSL certificates.
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    retries = Retry(total=None, connect=1, read=1, redirect=10, status=0, other=0)  # pylint: disable=E1123
    http = urllib3.PoolManager(cert_reqs='CERT_NONE', retries=retries)
    #
    # If regions hasn't already been defined, get the list of all the AWS
    # regions that support FSx for ONTAP.
    if len(config['regions']) == 0:  # pylint: disable=E0601
        ec2Client = boto3.client('ec2', config=boto3Config)
        ec2Regions = ec2Client.describe_regions()['Regions']
        for region in ec2Regions:
            config['regions'] += [region['RegionName']]
    fsxRegions = boto3.Session().get_available_regions('fsx')
    #
    # Discovery all the FSxNs. Including the ones in other accounts.
    fsxNs = []   # Holds the name and IP addresses of the FSxNs management ports.
    if config['scanCurrentAccount'] != "no":
        logger.debug("Scanning regions for FSxNs for the current account.")
        for region in config['regions']:
            if region in fsxRegions:
                logger.debug(f"    {region}")
                fsxClient = boto3.client('fsx', region_name=region, config=boto3Config)
                scanFsxNs(fsxClient)

    for accountRole in config['accountRoles']:
        logger.debug(f"Scanning regions for FSxNs for accountRole {accountRole}")
        for region in config['regions']:
            if region in fsxRegions:
                logger.debug(f"    {region}")
                sts_client = boto3.client('sts', region_name=region, config=boto3Config)

                assumed_role_object = sts_client.assume_role(
                        RoleArn=accountRole,
                        RoleSessionName="FSxCrossAccountSession"
                )
                credentials = assumed_role_object['Credentials']

                fsxClient = boto3.client('fsx',
                                         region_name=region,
                                         aws_access_key_id=credentials['AccessKeyId'],
                                         aws_secret_access_key=credentials['SecretAccessKey'],
                                         aws_session_token=credentials['SessionToken'],
                                         config=boto3Config)
                scanFsxNs(fsxClient)
                fsxClient.close()
                sts_client.close()                

    logger.debug(f"Found {len(fsxNs)} FSxNs.")
    if len(fsxNs) == 0:
        logger.error("No FSxNs found. Exiting.")
        return
    #
    # Get the last processed events stats file.
    try:
        logger.debug(f"Getting last processed events stats file.")
        response = s3Client.get_object(Bucket=config['s3BucketName'], Key=config['statsName'])
    except botocore.exceptions.ClientError as err:
        #
        # If the error is that the object doesn't exist, then this must be the
        # first time this script has run so create an empty lastProcessedStats.
        if err.response['Error']['Code'] == "NoSuchKey":
            lastProcessedStats = {}
        else:
            raise err
    else:
        lastProcessedStats = json.loads(response['Body'].read().decode('utf-8'))
    #
    # Process each FSxN.
    for fsxn in fsxNs:
        fsId = fsxn['name']
        fsIP = fsxn['IP']
        logger.debug(f"Checking {fsId}")
        #
        # Get the credentials.
        if secretARNs.get(fsId) is None and config['defaultSecretARN'] is not None:
            secretARNs[fsId] = config['defaultSecretARN']

        if secretARNs.get(fsId) is not None:
            #
            # Get the username and password of the ONTAP/FSxN system.
            try:
                secretsClient = boto3.client(service_name='secretsmanager', region_name=secretARNs[fsId].split(':')[3], config=boto3Config)
                secretsInfo = secretsClient.get_secret_value(SecretId=secretARNs[fsId])
                secret = json.loads(secretsInfo['SecretString'])
                if secret.get('username') is None or secret.get('password') is None:
                    logger.warning(f"The 'username' or 'password' keys were not found in the secret for '{fsId}' in the secretARN '{secretARNs[fsId]}'.")
                    continue
                username = secret['username']
                password = secret['password']
                secretsClient.close() # Since each secret could be in a different region.
            except botocore.exceptions.ClientError as err:
                logger.warning(f"Unable to retrieve the credentials for '{fsId}' using the secretARN '{secretARNs[fsId]}'. {err}")
                continue
        else:
            logger.warning(f'No secret ARN was found for {fsId}.')
            continue
        #
        # Create a header with the basic authentication.
        auth = urllib3.make_headers(basic_auth=f'{username}:{password}')
        headersQuery = { **auth }
        #
        # Get the last process event index for this FSxN.
        lastProcessed = lastProcessedStats.get(fsId)
        if lastProcessed is None:
            lastProcessed = {
                    'timestamp': 0,
                    'index': 0,
                    'ascTimestamp': "5m" # Only go back 5 minute if this hasn't been called before for this FSxN.
                    }
        #
        # Get the audit records.
        endpoint = f"/api/security/audit/messages?timestamp=>{lastProcessed['ascTimestamp']}&max_records=1000"
        while endpoint is not None:
            auditEvents = []
            try:
                logger.debug(f"Connecting to {fsIP}({fsId}) at {endpoint}")
                response = http.request('GET', f"https://{fsIP}{endpoint}", headers=headersQuery, timeout=15.0)
            except urllib3.exceptions.MaxRetryError as err:
                logger.warning(f"Unable to connect to {fsIP}({fsId}) at {endpoint}. {err}")
                break # Break out "while endpoint is not None" loop.
            except urllib3.exceptions.ConnectTimeoutError as err:
                logger.warning(f"Timeout connecting to {fsIP}({fsId}) at {endpoint}. {err}")
                break # Break out "while endpoint is not None" loop.
            if response.status == 200:
                data = json.loads(response.data.decode('utf-8'))
                logger.debug(f'Received {len(data["records"])} records from {fsIP}({fsId}).')
                for record in data['records']:
                    timestamp = getMsEpoch(record['timestamp'])
                    #
                    # First check that this is new event.
                    # While unlikely, the index could "roll over", so we need to check both the index and the timestamp.
                    if record['index'] > lastProcessed['index'] or timestamp > lastProcessed['timestamp']:
                        inputFilter = config["inputFilter"]
                        if inputFilter is None or inputFilter == "":
                            inputFilter = "ThisShouldn'tMatchAnything"
                        #
                        # Check that it is an event we want to record.
                        if (not re.search(inputFilter, record.get("input", "")) and
                          re.search(config['inputMatch'], record.get("input", "")) and
                          re.search(config['applicationMatch'], record.get("application", "")) and
                          re.search(config['userMatch'], record.get("user", "")) and
                          re.search(config['stateMatch'], record.get("state", ""))):
                            lastAscTimestamp = record['timestamp']
                            lastIndex = record['index']
                            message = f'{record["timestamp"]} Node:{record["node"]["name"]} location:{record.get("location", "N/A")} application:{record.get("application", "N/A")} user:{record.get("user", "N/A")} state:{record.get("state", "N/A")} scope:{record.get("scope", "N/A")} input:{record.get("input", "N/A")}'
                            auditEvents.append({'timestamp': timestamp, 'message': message})
                #
                # If we have any events, then put them in CloudWatch.
                if len(auditEvents) > 0:
                    logger.debug(f"Adding {len(auditEvents)} events for {fsId} with index {lastIndex} and timestamp {lastAscTimestamp}")
                    putEventInCloudWatch(auditEvents, f"{fsId}-{datetime.datetime.now().strftime('%Y-%m-%d')}")
                    lastProcessed['timestamp'] = timestamp
                    lastProcessed['ascTimestamp'] = lastAscTimestamp
                    lastProcessed['index'] = lastIndex
                    lastProcessedStats[fsId] = lastProcessed
                    s3Client.put_object(Key=config['statsName'], Bucket=config['s3BucketName'], Body=json.dumps(lastProcessedStats).encode('UTF-8'))
                #
                # Check to see if there are any more.
                endpoint = data['_links']['next']['href'] if 'next' in data['_links'] else None
            else:
                logger.error(f"API call to https://{fsIP}{endpoint} failed. HTTP status code: {response.status}.")
                break # Break out "while endpoint is not None" loop.
#
# If this script is not running as a Lambda function, then call the lambda_handler function.
lambdaFunction = True
if os.environ.get('AWS_LAMBDA_FUNCTION_NAME') == None:
    lambdaFunction = False
    lambda_handler(None, None)
