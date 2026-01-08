#!/bin/python3
################################################################################
# THIS SOFTWARE IS PROVIDED BY NETAPP "AS IS" AND ANY EXPRESS OR IMPLIED
# WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO
# EVENT SHALL NETAPP BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS;
# OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR'
# OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
################################################################################
#
################################################################################
# This program is used to monitor some of Data ONTAP services (EMS Message,
# Snapmirror relationships, quotas) running under AMS, and alert on any
# "matching conditions."  It is intended to be run as a Lambda function, but
# can be run as a standalone program.
#
# Version: %%VERSION%%
# Date: %%DATE%%
################################################################################

import json
import re
import os
import datetime
import pytz
import logging
from logging.handlers import SysLogHandler
from cronsim import CronSim
import urllib3
from urllib3.util import Retry
import botocore
import boto3
import hashlib

eventResilience = 4 # Times an event has to be missing before it is removed
                    # from the alert history.
                    # This was added since the Ontap API that returns EMS
                    # events would often drop some events and then including
                    # them in the subsequent calls. If I don't "age" the
                    # alert history duplicate alerts will be sent.
initialVersion = "Initial Run"  # The version to store if this is the first
                                # time the program has been run against a
                                # FSxN.

################################################################################
# This function is used to extract a number from the string passed in, starting
# at the 'start' character. Then, multiple it by the unit after the number:
# D = Day = 60*60*24
# H = Hour = 60*60
# M = Minutes = 60
#
# It returns a tuple that has the extracted number and the end position.
################################################################################
def getNumber(string, start):

    global logger, clusterName

    if len(string) <= start:
        return (0, start)
    #
    # Check to see how many digits are in the number.
    end = start
    while re.search('[0-9]', string[end:end+1]) and end < len(string):
        end += 1

    num=int(string[start:end])
    endp1=end+1
    if string[end:endp1] == "D":
        num=num*60*60*24
    elif string[end:endp1] == "H":
        num=num*60*60
    elif string[end:endp1] == "M":
        num=num*60
    elif string[end:endp1] != "S":
        logger.warning(f'Unknown lag time specifier "{string[end:endp1]} found on cluster {clusterName}".')

    return (num, endp1)

################################################################################
# This function is used to parse the lag time string returned by the
# ONTAP API and return the equivalent seconds it represents.
# The input string is assumed to follow this pattern "P#DT#H#M#S" where
# each of those "#" can be one to three digits long. Also, if the lag isn't
# more than 24 hours, then the "#D" isn't there and the string simply starts
# with "PT". Similarly, if the lag time isn't more than an hour then the "#H"
# string is missing.
################################################################################
def parseLagTime(string):
    #
    num=0
    #
    # First check to see if the Day field is there, by checking to see if the
    # second character is a digit. If not, it is assumed to be 'T'.
    includesDay=False
    if re.search('[0-9]', string[1:2]):
        includesDay=True
        start=1
    else:
        start=2
    data=getNumber(string, start)
    num += data[0]

    start=data[1]
    #
    # If there is a 'D', then there is a 'T' between the D and the # of hours
    # so skip pass it.
    if includesDay:
        start += 1
    data=getNumber(string, start)
    num += data[0]

    start=data[1]
    data=getNumber(string, start)
    num += data[0]

    start=data[1]
    data=getNumber(string, start)
    num += data[0]

    return(num)

################################################################################
# This function checks to see if an event is in the events array based on
# the unique identifier passed in. If it is found, it will return the index
# of the matching entry, otherwise it returns -1.
################################################################################
def eventExist (events, uniqueIdentifier):
    for i in range(len(events)):
        if events[i]["index"] == uniqueIdentifier:
            return i

    return -1

################################################################################
# This function makes an API call to the FSxN to ensure it is up. If the
# errors out, then it sends an alert, and returns 'False'. Otherwise it returns
# 'True'.
################################################################################
def checkSystem():
    global config, s3Client, snsClient, http, headers, clusterName, clusterVersion, logger, clusterTimezone

    changedEvents = False
    #
    # Get the previous status.
    try:
        data = s3Client.get_object(Key=config["systemStatusFilename"], Bucket=config["s3BucketName"])
    except botocore.exceptions.ClientError as err:
        # If the error is that the object doesn't exist, then this must be the
        # first time this script has run against thie filesystem so create an
        # initial status structure.
        if err.response['Error']['Code'] == "NoSuchKey":
            fsxStatus = {
                "systemHealth": 0,
                "version" : initialVersion,
                "numberNodes" : 2,
                "downInterfaces" : []
            }
            changedEvents = True
        else:
            raise Exception(err)
    else:
        fsxStatus = json.loads(data["Body"].read().decode('UTF-8'))
    #
    # Get the cluster name, ONTAP version and timezone from the FSxN.
    # This is also a way to test that the FSxN cluster is accessible.
    badHTTPStatus = False
    try:
        endpoint = f'https://{config["OntapAdminServer"]}/api/cluster?fields=version,name,timezone'
        response = http.request('GET', endpoint, headers=headers, timeout=5.0)
        if response.status == 200:
            if fsxStatus["systemHealth"] != 0:
                fsxStatus["systemHealth"] = 0
                changedEvents = True

            data = json.loads(response.data)
            if config["awsAccountId"] != None:
                clusterName = f'{data["name"]}({config["awsAccountId"]})'
            else:
                clusterName = data['name']
            #
            # The following assumes that the format of the "full" version
            # looks like: "NetApp Release 9.13.1P6: Tue Dec 05 16:06:25 UTC 2023".
            # The reason for looking at the "full" instead of the individual
            # keys (generation, major, minor) is because they don't provide
            # the patch level. :-(
            clusterVersion = data["version"]["full"].split()[2].replace(":", "")
            if fsxStatus["version"] == initialVersion:
                fsxStatus["version"] = clusterVersion
            #
            # Get the Timezone for SnapMirror lag time calculations.
            clusterTimezone = data["timezone"]["name"]
        else:
            badHTTPStatus = True
            raise Exception(f'API call to {endpoint} failed. HTTP status code: {response.status}.')
    except:
        logger.debug(f'Failed to issue API against {config["OntapAdminServer"]}.', exc_info=True)
        if fsxStatus["systemHealth"] == 1:  # 1 == second failure.
            if config["awsAccountId"] != None:
                clusterName = f'{config["OntapAdminServer"]}({config["awsAccountId"]})'
            else:
                clusterName = config["OntapAdminServer"]
            if badHTTPStatus:
                message = f'CRITICAL: Received a non 200 HTTP status code ({response.status}) when trying to access {clusterName}.'
            else:
                message = f'CRITICAL: Failed to issue API against {clusterName}. Cluster could be down.'
            sendAlert(message, "CRITICAL")
            fsxStatus["systemHealth"] += 1
            changedEvents = True

        if fsxStatus["systemHealth"] == 0:
            fsxStatus["systemHealth"] += 1
            changedEvents = True

    if changedEvents:
        s3Client.put_object(Key=config["systemStatusFilename"], Bucket=config["s3BucketName"], Body=json.dumps(fsxStatus).encode('UTF-8'))
    #
    # If the cluster is done, return false so the program can exit cleanly.
    return fsxStatus["systemHealth"] == 0

################################################################################
# This function checks the following things:
#   o If the ONTAP version has changed.
#   o If one of the nodes are down.
#   o If a network interface is down.
#
# ASSUMPTIONS: That checkSystem() has been called before it.
################################################################################
def checkSystemHealth(service):
    global config, s3Client, snsClient, http, headers, clusterName, clusterVersion, logger

    changedEvents = False
    #
    # Get the previous status.
    # Shouldn't have to check for status of the get_object() call, to see if the object exist or not,
    # since "checkSystem()" should already have been called and it creates the object if it doesn't
    # already exist. So, if there is a failure, it should be something else than "non-existent".
    data = s3Client.get_object(Key=config["systemStatusFilename"], Bucket=config["s3BucketName"])
    fsxStatus = json.loads(data["Body"].read().decode('UTF-8'))

    for rule in service["rules"]:
        for key in rule.keys():
            lkey = key.lower()
            if lkey == "versionchange":
                if rule[key] and clusterVersion != fsxStatus["version"]:
                    message = f'NOTICE: The ONTAP vesion changed on cluster {clusterName} from {fsxStatus["version"]} to {clusterVersion}.'
                    sendAlert(message, "INFO")
                    fsxStatus["version"] = clusterVersion
                    changedEvents = True
            elif lkey == "failover":
                #
                # Check that both nodes are available.
                # Using the CLI passthrough API because I couldn't find the equivalent API call.
                if rule[key]:
                    endpoint = f'https://{config["OntapAdminServer"]}/api/private/cli/system/node/virtual-machine/instance/show-settings'
                    response = http.request('GET', endpoint, headers=headers)
                    if response.status == 200:
                        data = json.loads(response.data)
                        if data["num_records"] != fsxStatus["numberNodes"]:
                            message = f'Alert: The number of nodes in cluster {clusterName} went from {fsxStatus["numberNodes"]} to {data["num_records"]}.\nNote, this is likely a planned failover event to upgrade the O/S, or to change the throughput capacity.'
                            sendAlert(message, "INFO")
                            fsxStatus["numberNodes"] = data["num_records"]
                            changedEvents = True
                    else:
                        logger.warning(f'API call to {endpoint} failed. HTTP status code: {response.status}.')
            elif lkey == "networkinterfaces":
                if rule[key]:
                    endpoint = f'https://{config["OntapAdminServer"]}/api/network/ip/interfaces?fields=state'
                    response = http.request('GET', endpoint, headers=headers)
                    if response.status == 200:
                        #
                        # Decrement the refresh field to know if any events have really gone away.
                        for interface in fsxStatus["downInterfaces"]:
                            interface["refresh"] -= 1

                        data = json.loads(response.data)
                        for interface in data["records"]:
                            if interface.get("state") != None and interface["state"] != "up":
                                uniqueIdentifier = interface["name"]
                                eventIndex = eventExist(fsxStatus["downInterfaces"], uniqueIdentifier)
                                if eventIndex < 0:
                                    message = f'Alert: Network interface {interface["name"]} on cluster {clusterName} is down.'
                                    sendAlert(message, "WARNING")
                                    event = {
                                        "index": uniqueIdentifier,
                                        "refresh": eventResilience
                                    }
                                    fsxStatus["downInterfaces"].append(event)
                                    changedEvents = True
                                else:
                                    #
                                    # If the event was found, reset the refresh count. If it is just one less
                                    # than the max, then it means it was decremented above so there wasn't
                                    # really a change in state.
                                    if fsxStatus["downInterfaces"][eventIndex]["refresh"] != (eventResilience - 1):
                                        changedEvents = True
                                    fsxStatus["downInterfaces"][eventIndex]["refresh"] = eventResilience
                        #
                        # After processing the records, see if any events need to be removed.
                        i = len(fsxStatus["downInterfaces"]) - 1
                        while i >= 0:
                            if fsxStatus["downInterfaces"][i]["refresh"] <= 0:
                                logger.debug(f'Deleting interface: {fsxStatus["downInterfaces"][i]["index"]} Cluster={clusterName}')
                                del fsxStatus["downInterfaces"][i]
                                changedEvents = True
                            else:
                                if fsxStatus["downInterfaces"][i]["refresh"] != eventResilience:
                                    changedEvents = True
                            i -= 1
                    else:
                        logger.warning(f'API call to {endpoint} failed. HTTP status code: {response.status}.')
            else:
                logger.warning(f'Unknown System Health alert type: "{key}" found on cluster {clusterName}.')

    if changedEvents:
        s3Client.put_object(Key=config["systemStatusFilename"], Bucket=config["s3BucketName"], Body=json.dumps(fsxStatus).encode('UTF-8'))

################################################################################
# This function processes the EMS events.
################################################################################
def processEMSEvents(service):
    global config, s3Client, snsClient, http, headers, clusterName, clusterVersion, logger

    changedEvents = False
    #
    # Get the saved events so we can ensure we are only reporting on new ones.
    try:
        data = s3Client.get_object(Key=config["emsEventsFilename"], Bucket=config["s3BucketName"])
    except botocore.exceptions.ClientError as err:
        # If the error is that the object doesn't exist, then it will get created once an alert it sent.
        if err.response['Error']['Code'] == "NoSuchKey":
            events = []
        else:
            raise Exception(err)
    else:
        events = json.loads(data["Body"].read().decode('UTF-8'))
    #
    # Decrement the refresh field to know if any records have really gone away.
    for event in events:
        event["refresh"] -= 1
    #
    # Run the API call to get the current list of EMS events.
    records = []
    url = '/api/support/ems/events?return_timeout=15'
    while url is not None:
        endpoint = f'https://{config["OntapAdminServer"]}{url}'
        response = http.request('GET', endpoint, headers=headers)
        if response.status == 200:
            data = json.loads(response.data)
            records.extend(data.get("records"))
        else:
            logger.warning(f'API call to {endpoint} failed. HTTP status code: {response.status}.')
            return  #  Don't age out any events if we weren't able to get the current list.

        if data.get("_links") is not None and data["_links"].get("next") is not None and data["_links"]["next"].get("href") is not None:
            url = data["_links"]["next"]["href"]
        else:
            url = None
    #
    # Process the events to see if there are any new ones.
    print(f'Received {len(records)} EMS records.')
    logger.info(f'Received {len(records)} EMS records from cluster {clusterName}.')
    for record in records:
        for rule in service["rules"]:
            messageFilter = rule.get("filter")
            if messageFilter == None or messageFilter == "":
                messageFilter = "ThisShouldn'tMatchAnything"

            if (not re.search(messageFilter, record["log_message"]) and
                re.search(rule["name"], record["message"]["name"]) and
                re.search(rule["severity"], record["message"]["severity"]) and
                re.search(rule["message"], record["log_message"])):
                eventIndex = eventExist (events, record["index"])
                if eventIndex < 0:
                    message = f'{record["time"]} : {clusterName} {record["message"]["name"]}({record["message"]["severity"]}) - {record["log_message"]}'
                    useverity=record["message"]["severity"].upper()
                    if useverity == "EMERGENCY":
                        sendAlert(message, "CRITICAL")
                    elif useverity == "ALERT":
                        sendAlert(message, "ERROR")
                    elif useverity == "ERROR":
                        sendAlert(message, "WARNING")
                    elif useverity == "NOTICE" or useverity == "INFORMATIONAL":
                        sendAlert(message, "INFO")
                    elif useverity == "DEBUG":
                        sendAlert(message, "DEBUG")
                    else:
                        sendAlert(f'Received unknown severity from ONTAP "{record["message"]["severity"]}". The message received is next.', "INFO")
                        sendAlert(message, "INFO")

                    changedEvents = True
                    event = {
                            "index": record["index"],
                            "time": record["time"],
                            "messageName": record["message"]["name"],
                            "message": record["log_message"],
                            "refresh": eventResilience
                            }
                    events.append(event)
                else:
                    #
                    # If the event was found, reset the refresh count. If it is just one less
                    # than the max, then it means it was decremented above so there wasn't
                    # really a change in state.
                    if events[eventIndex]["refresh"] != (eventResilience - 1):
                        changedEvents = True
                    events[eventIndex]["refresh"] = eventResilience
    #
    # Now that we have processed all the events, check to see if any events should be deleted.
    i = len(events) - 1
    while i >= 0:
        if events[i]["refresh"] <= 0:
            logger.debug(f'Deleting event: {events[i]["time"]} : {events[i]["message"]} Cluster={clusterName}')
            del events[i]
            changedEvents = True
        else:
            # If an event wasn't refreshed, then we need to save the new refresh count.
            if events[i]["refresh"] != eventResilience:
                changedEvents = True
        i -= 1
    #
    # If the events array changed, save it.
    if changedEvents:
        s3Client.put_object(Key=config["emsEventsFilename"], Bucket=config["s3BucketName"], Body=json.dumps(events).encode('UTF-8'))

################################################################################
# This function is used to find an existing SM relationship based on the source
# and destinatino path passed in. It returns None if one isn't found
################################################################################
def getPreviousSMRecord(relationShips, uuid):
    for relationship in relationShips:
        if relationship.get('uuid') == uuid:
            relationship['refresh'] = True
            return(relationship)

    return(None)

################################################################################
# This function will convert seconds into an ascii string of number days, hours,
# minutes, and seconds. It will return the string.
################################################################################
def lagTimeStr(seconds):
    days = seconds // (60 * 60 * 24)
    seconds = seconds - (days * (60 * 60 * 24))
    hours = seconds // (60 * 60)
    seconds = seconds - (hours * (60 * 60))
    minutes = seconds // 60
    seconds = seconds - (minutes * 60)

    timeStr=""
    if days > 0:
        plural = "s" if days != 1 else ""
        timeStr = f'{days} day{plural} '
    if hours > 0 or days > 0:
        plural = "s" if hours != 1 else ""
        timeStr += f'{hours} hour{plural} '
    if minutes > 0 or days > 0 or hours > 0:
        plural = "s" if minutes != 1 else ""
        timeStr += f'{minutes} minute{plural} and '
    plural = "s" if seconds != 1 else ""
    timeStr += f'{seconds} second{plural}'
    return timeStr

################################################################################
# This function converts an array of numbers to a comma separated string. If
# the array is empty, it returns "*".
################################################################################
def convertArrayToString(array):

    text = ""
    for item in array:
        if text != "":
             text += ","
        text += str(item)

    return text if text != "" else "*"

################################################################################
# This function takes a schedule dictionary and returns the last time it should
# run. It returns the time in seconds since the UNIX epoch.
################################################################################
def getLastRunTime(scheduleUUID):
    global config, http, headers, clusterName, clusterVersion, logger, clusterTimezone

    minutes = ""
    hours = ""
    months = ""
    daysOfMonth = ""
    daysOfWeek = ""
    #
    # Run the API call to get the schedule information.
    endpoint = f'https://{config["OntapAdminServer"]}/api/cluster/schedules/{scheduleUUID}?fields=*&return_timeout=15'
    response = http.request('GET', endpoint, headers=headers)
    if response.status == 200:
        schedule = json.loads(response.data)

        if schedule['cron'].get("minutes") is not None:
            minutes = convertArrayToString(schedule['cron']['minutes'])
        else:
            minutes = "*"

        if schedule['cron'].get("hours") is not None:
            hours = convertArrayToString(schedule['cron']['hours'])
        else:
            hours = "*"

        if schedule['cron'].get("days") is not None:
            daysOfMonth = convertArrayToString(schedule['cron']['days'])
        else:
            daysOfMonth = "*"

        if schedule['cron'].get("months") is not None:
            months = convertArrayToString(schedule['cron']['months'])
        else:
            months = "*"

        if schedule['cron'].get("weekdays") is not None:
            daysOfWeek = convertArrayToString(schedule['cron']['weekdays'])
        else:
            daysOfWeek = "*"
        #
        # Create the cron expression.
        cron_expression = f"{minutes} {hours} {daysOfMonth} {months} {daysOfWeek}"
        #
        # Initialize CronSim with the cron expression and current time.
        curTime = datetime.datetime.now(pytz.timezone(clusterTimezone) if clusterTimezone != None else datetime.timezone.utc)
        curTimeSec = curTime.timestamp()
        it = CronSim(cron_expression, curTime, reverse=True)
        #
        # Get the last run time.
        lastRunTime = next(it)
        lastRunTimeSec = lastRunTime.timestamp()
        return int(lastRunTimeSec)
    else:
        logger.error(f'API call to {endpoint} failed. HTTP status code: {response.status}.')
        return -1

################################################################################
################################################################################
def getPolicySchedule(policyUUID):
    global config, http, headers, clusterName, clusterVersion, logger

    # Run the API call to get the policy information.
    endpoint = f'https://{config["OntapAdminServer"]}/api/snapmirror/policies/{policyUUID}?fields=*&return_timeout=15'
    response = http.request('GET', endpoint, headers=headers)
    if response.status == 200:
        data = json.loads(response.data)
        if data.get('transfer_schedule') != None:
            return data['transfer_schedule']['uuid']
        else:
            return None
    else:
        logger.error(f'API call to {endpoint} failed. HTTP status code: {response.status}.')
        return None

################################################################################
# This function is used to find the last time a SnapMirror relationship should
# have been updated. It returns the time in seconds since the UNIX epoch.
################################################################################
def getLastScheduledUpdate(record):
    global config, http, headers, clusterName, clusterVersion, logger
    #
    # First check to see if there is a schedule associated with the SM relationship.
    if record.get("transfer_schedule") is not None:
        lastRunTime = getLastRunTime(record["transfer_schedule"]["uuid"])
    else:
        #
        # If there is no schedule at the relationship level, check to see
        # if the policy has one.
        scheduleUUID = getPolicySchedule(record["policy"]["uuid"])
        if scheduleUUID is not None:
            lastRunTime = getLastRunTime(scheduleUUID)
        else:
            lastRunTime = -1
    return lastRunTime

################################################################################
# This function is used to check SnapMirror relationships.
################################################################################
def processSnapMirrorRelationships(service):
    global config, s3Client, snsClient, http, headers, clusterName, clusterVersion, logger, clusterTimezone
    #
    # Get the saved events so we can ensure we are only reporting on new ones.
    try:
        data = s3Client.get_object(Key=config["smEventsFilename"], Bucket=config["s3BucketName"])
    except botocore.exceptions.ClientError as err:
        # If the error is that the object doesn't exist, then it will get created once an alert is sent.
        if err.response['Error']['Code'] == "NoSuchKey":
            events = []
        else:
            raise Exception(err)
    else:
        events = json.loads(data["Body"].read().decode('UTF-8'))
    #
    # Decrement the refresh field to know if any records have really gone away.
    for event in events:
        event["refresh"] -= 1

    changedEvents=False
    #
    # Get the saved SM relationships.
    try:
        data = s3Client.get_object(Key=config["smRelationshipsFilename"], Bucket=config["s3BucketName"])
    except botocore.exceptions.ClientError as err:
        # If the error is that the object doesn't exist, then it will get created once an alert is sent.
        if err.response['Error']['Code'] == "NoSuchKey":
            smRelationships = []
        else:
            raise Exception(err)
    else:
        smRelationships = json.loads(data["Body"].read().decode('UTF-8'))
    #
    # Set the refresh to False to know if any of the relationships still exist.
    for relationship in smRelationships:
        relationship["refresh"] = False

    updateRelationships = False
    #
    # Get the current time in seconds since UNIX epoch 01/01/1970.
    curTimeSeconds = int(datetime.datetime.now(pytz.timezone(clusterTimezone) if clusterTimezone != None else datetime.timezone.utc).timestamp())
    #
    # Consolidate all the rules so we can decide how to process lagtime.
    maxLagTime = None
    maxLagTimePercent = None
    healthy = None
    stalledTransferSeconds = None
    offline = None
    for rule in service["rules"]:
        for key in rule.keys():
            lkey = key.lower()
            if lkey == "maxlagtime":
                maxLagTime = rule[key]
                maxLagTimeKey = key
            elif lkey == "maxlagtimepercent":
                maxLagTimePercent = rule[key]
                maxLagTimePercentKey = key
            elif lkey == "healthy":
                healthy = rule[key]
                healthyKey = key
            elif lkey == "stalledtransferseconds":
                stalledTransferSeconds = rule[key]
                stalledTransferSecondsKey = key
            else:
                logger.warning(f'Unknown snapmirror alert type: "{key}" found on cluster {clusterName}.')
    #
    # Run the API call to get the current state of all the snapmirror relationships.
    url = f'/api/snapmirror/relationships?fields=*&return_timeout=15'
    records = []
    while url is not None:
        endpoint = f'https://{config["OntapAdminServer"]}{url}'
        response = http.request('GET', endpoint, headers=headers)
        if response.status == 200:
            data = json.loads(response.data)
            records.extend(data.get("records"))
        else:
            logger.warning(f'API call to {endpoint} failed. HTTP status code: {response.status}.')
            return

        if data.get("_links") is not None and data["_links"].get("next") is not None and data["_links"]["next"].get("href") is not None:
            url = data["_links"]["next"]["href"]
        else:
            url = None

    logger.info(f'Found {len(records)} SnapMirror relationships on cluster {clusterName}.')
    for record in records:
        #
        # Since there are multiple ways to process lag time, make sure to only do it one way for each relationship.
        processedLagTime = False
        #
        # If the source cluster isn't defined, then assume it is a local SM relationship.
        if record['source'].get('cluster') is None:
            sourceClusterName = clusterName
        else:
            sourceClusterName = record['source']['cluster']['name']
        #
        # For lag time if maxLagTimePercent is defined check to see if there is a schedule,
        # if there is a schedule alert on that otherrwise alert on the maxLagTime.
        # But, first check that lag_time is defined, and that the state is not "uninitialized",
        # since the lag_time is set to the oldest snapshot of the source volume which would
        # cause a false positive.
        if record.get("lag_time") is not None and record["state"].lower() != "uninitialized":
            lagSeconds = parseLagTime(record["lag_time"])
            if maxLagTimePercent is not None:
                lastScheduledUpdate = getLastScheduledUpdate(record)
                if lastScheduledUpdate != -1:
                    processedLagTime = True
                    if lagSeconds > ((curTimeSeconds - lastScheduledUpdate) * maxLagTimePercent/100):
                        #
                        # If the transfer is in progress, and they have stalled transfer alert enabled, we don't need to alert on the lag time.
                        if not (record.get("transfer") is not None and record["transfer"]["state"].lower() in ["transferring", "finalizing", "preparing", "fasttransferring"] and stalledTransferSeconds is not None):
                            uniqueIdentifier = record["uuid"] + "_" + maxLagTimePercentKey
                            eventIndex = eventExist(events, uniqueIdentifier)
                            if eventIndex < 0:
                                timeStr = lagTimeStr(lagSeconds)
                                asciiTime = datetime.datetime.fromtimestamp(lastScheduledUpdate).strftime('%Y-%m-%d %H:%M:%S')
                                message = f'Snapmirror Lag Alert: {sourceClusterName}::{record["source"]["path"]} -> {clusterName}::{record["destination"]["path"]} has a lag time of {lagSeconds} seconds ({timeStr}) which is more than {maxLagTimePercent}% of its last scheduled update at {asciiTime}.'
                                sendAlert(message, "WARNING")
                                changedEvents=True
                                event = {
                                    "index": uniqueIdentifier,
                                    "message": message,
                                    "refresh": eventResilience
                                }
                                events.append(event)
                            else:
                                # If the event was found, reset the refresh count. If it is just one less
                                # than the max, then it means it was decremented above so there wasn't
                                # really a change in state.
                                if events[eventIndex]["refresh"] != (eventResilience - 1):
                                    changedEvents = True
                                events[eventIndex]["refresh"] = eventResilience

            if maxLagTime is not None and not processedLagTime:
                if lagSeconds > maxLagTime:
                    uniqueIdentifier = record["uuid"] + "_" + maxLagTimeKey
                    eventIndex = eventExist(events, uniqueIdentifier)
                    if eventIndex < 0:
                        timeStr = lagTimeStr(lagSeconds)
                        message = f'Snapmirror Lag Alert: {sourceClusterName}::{record["source"]["path"]} -> {clusterName}::{record["destination"]["path"]} has a lag time of {lagSeconds} seconds, or {timeStr} which is more than {maxLagTime}.'
                        sendAlert(message, "WARNING")
                        changedEvents=True
                        event = {
                            "index": uniqueIdentifier,
                            "message": message,
                            "refresh": eventResilience
                        }
                        events.append(event)
                    else:
                        # If the event was found, reset the refresh count. If it is just one less
                        # than the max, then it means it was decremented above so there wasn't
                        # really a change in state.
                        if events[eventIndex]["refresh"] != (eventResilience - 1):
                            changedEvents = True
                        events[eventIndex]["refresh"] = eventResilience

        if healthy is not None:
            if not healthy and not record["healthy"]: # Report on "not healthy" and the status is "not healthy"
                uniqueIdentifier = record["uuid"] + "_" + healthyKey
                eventIndex = eventExist(events, uniqueIdentifier)
                if eventIndex < 0:
                    message = f'Snapmirror Health Alert: {sourceClusterName}::{record["source"]["path"]} {clusterName}::{record["destination"]["path"]} has a status of {record["healthy"]}.'
                    for reason in record["unhealthy_reason"]:
                        message += "\n" + reason["message"]
                    sendAlert(message, "WARNING")
                    changedEvents=True
                    event = {
                        "index": uniqueIdentifier,
                        "message": message,
                        "refresh": eventResilience
                    }
                    events.append(event)
                else:
                    # If the event was found, reset the refresh count. If it is just one less
                    # than the max, then it means it was decremented above so there wasn't
                    # really a change in state.
                    if events[eventIndex]["refresh"] != (eventResilience - 1):
                        changedEvents = True
                    events[eventIndex]["refresh"] = eventResilience

        if stalledTransferSeconds is not None:
            if record.get('transfer') is not None and record['transfer']['state'].lower() == "transferring":
                transferUuid = record['transfer']['uuid']
                bytesTransferred = record['transfer']['bytes_transferred']
                prevRec =  getPreviousSMRecord(smRelationships, transferUuid) # This reset the "refresh" field if found.
                if prevRec != None:
                    timeDiff=curTimeSeconds - prevRec["time"]
                    if prevRec['bytesTransferred'] == bytesTransferred:
                        if (curTimeSeconds - prevRec['time']) > stalledTransferSeconds:
                            uniqueIdentifier = record['uuid'] + "_" + "transfer"
                            eventIndex = eventExist(events, uniqueIdentifier)
                            if eventIndex < 0:
                                message = f"Snapmirror transfer has stalled: {sourceClusterName}::{record['source']['path']} -> {clusterName}::{record['destination']['path']}."
                                sendAlert(message, "WARNING")
                                changedEvents=True
                                event = {
                                    "index": uniqueIdentifier,
                                    "message": message,
                                    "refresh": eventResilience
                                }
                                events.append(event)
                            else:
                                # If the event was found, reset the refresh count. If it is just one less
                                # than the max, then it means it was decremented above so there wasn't
                                # really a change in state.
                                if events[eventIndex]["refresh"] != (eventResilience - 1):
                                    changedEvents = True
                                events[eventIndex]["refresh"] = eventResilience
                    else:
                        prevRec['time'] = curTimeSeconds
                        prevRec['refresh'] = True
                        prevRec['bytesTransferred'] = bytesTransferred
                        updateRelationships = True
                else:
                    prevRec = {
                        "time": curTimeSeconds,
                        "refresh": True,
                        "bytesTransferred": bytesTransferred,
                        "uuid": transferUuid
                    }
                    updateRelationships = True
                    smRelationships.append(prevRec)
    #
    # After processing the records, see if any SM relationships need to be removed.
    i = len(smRelationships) - 1
    while i >= 0:
        if not smRelationships[i]["refresh"]:
            relationshipId = smRelationships[i].get("uuid")
            if relationshipId is None:
                id="Old format"
            else:
                id = relationshipId
            logger.debug(f'Deleting smRelationship: {id} cluster={clusterName}')
            del smRelationships[i]
            updateRelationships = True

        i -= 1
    #
    # If any of the SM relationships changed, save it.
    if(updateRelationships):
        s3Client.put_object(Key=config["smRelationshipsFilename"], Bucket=config["s3BucketName"], Body=json.dumps(smRelationships).encode('UTF-8'))
    #
    # After processing the records, see if any events need to be removed.
    i = len(events) - 1
    while i >= 0:
        if events[i]["refresh"] <= 0:
            logger.debug(f'Deleting event: {events[i]["message"]} Cluster={clusterName}')
            del events[i]
            changedEvents = True
        else:
            # If an event wasn't refreshed, then we need to save the new refresh count.
            if events[i]["refresh"] != eventResilience:
                changedEvents = True
        i -= 1
    #
    # If the events array changed, save it.
    if(changedEvents):
        s3Client.put_object(Key=config["smEventsFilename"], Bucket=config["s3BucketName"], Body=json.dumps(events).encode('UTF-8'))

################################################################################
# This function is used to check all the volume and aggregate utlization.
################################################################################
def processStorageUtilization(service):
    global config, s3Client, snsClient, http, headers, clusterName, clusterVersion, logger, clusterTimezone

    changedEvents=False
    #
    # Get the saved events so we can ensure we are only reporting on new ones.
    try:
        data = s3Client.get_object(Key=config["storageEventsFilename"], Bucket=config["s3BucketName"])
    except botocore.exceptions.ClientError as err:
        # If the error is that the object doesn't exist, then it will get created once an alert it sent.
        if err.response['Error']['Code'] == "NoSuchKey":
            events = []
        else:
            raise Exception(err)
    else:
        events = json.loads(data["Body"].read().decode('UTF-8'))
    #
    # Decrement the refresh field to know if any records have really gone away.
    for event in events:
        event["refresh"] -= 1
    #
    # Run the API call to get the physical storage used.
    url = '/api/storage/aggregates?fields=space&return_timeout=15'
    aggrRecords = []
    while url is not None:
        endpoint = f'https://{config["OntapAdminServer"]}{url}'
        aggrResponse = http.request('GET', endpoint, headers=headers)
        if aggrResponse.status != 200:
            logger.error(f'API call to {endpoint} failed. HTTP status code {aggrResponse.status}.')
            break
        else:
            data = json.loads(aggrResponse.data)
            aggrRecords.extend(data.get("records"))
            if data.get("_links") is not None and data["_links"].get("next") is not None and data["_links"]["next"].get("href") is not None:
                url = data["_links"]["next"]["href"]
            else:
                url = None
    #
    # Run the API call to get the volume information.
    url = '/api/storage/volumes?fields=style,flexcache_endpoint_type,space,files,svm,state&return_timeout=15'
    volumeRecords = []
    while url is not None:
        endpoint = f'https://{config["OntapAdminServer"]}{url}'
        volumeResponse = http.request('GET', endpoint, headers=headers)
        if volumeResponse.status != 200:
            logger.error(f'API call to {endpoint} failed. HTTP status code {volumeResponse.status}.')
            break
        else:
            data = json.loads(volumeResponse.data)
            volumeRecords.extend(data.get("records"))
            if data.get("_links") is not None and data["_links"].get("next") is not None and data["_links"]["next"].get("href") is not None:
                url = data["_links"]["next"]["href"]
            else:
                url = None
    #
    # Now get the constituent volumes.
    url = '/api/storage/volumes?is_constituent=true&fields=style,flexcache_endpoint_type,space,files,svm,state&return_timeout=15'
    while url is not None:
        endpoint = f'https://{config["OntapAdminServer"]}{url}'
        volumeResponse = http.request('GET', endpoint, headers=headers)
        if volumeResponse.status != 200:
            logger.error(f'API call to {endpoint} failed. HTTP status code {volumeResponse.status}.')
            break
        else:
            data = json.loads(volumeResponse.data)
            volumeRecords.extend(data.get("records"))
            if data.get("_links") is not None and data["_links"].get("next") is not None and data["_links"]["next"].get("href") is not None:
                url = data["_links"]["next"]["href"]
            else:
                url = None

    logger.info(f'Found {len(volumeRecords)} volumes and {len(aggrRecords)} aggregates to check on cluster {clusterName}.')
    #
    # If there are no volumes or aggregates, there is nothing to do.
    if len(volumeRecords) == 0 and len(aggrRecords) == 0:
        return

    for rule in service["rules"]:
        for key in rule.keys():
            lkey=key.lower()
            if lkey == "aggrwarnpercentused" or lkey == 'aggrcriticalpercentused':
                for aggr in aggrRecords:
                    if aggr["space"]["block_storage"]["used_percent"] >= rule[key]:
                        uniqueIdentifier = aggr["uuid"] + "_" + key
                        eventIndex = eventExist(events, uniqueIdentifier)
                        if eventIndex < 0:
                            alertType = 'Warning' if lkey == "aggrwarnpercentused" else 'Critical'
                            message = f'Aggregate {alertType} Alert: Aggregate {aggr["name"]} on {clusterName} is {aggr["space"]["block_storage"]["used_percent"]}% full, which is more or equal to {rule[key]}% full.'
                            sendAlert(message, "WARNING")
                            changedEvents = True
                            event = {
                                    "index": uniqueIdentifier,
                                    "message": message,
                                    "refresh": eventResilience
                                }
                            events.append(event)
                        else:
                            # If the event was found, reset the refresh count. If it is just one less
                            # than the max, then it means it was decremented above so there wasn't
                            # really a change in state.
                            if events[eventIndex]["refresh"] != (eventResilience - 1):
                                changedEvents = True
                            events[eventIndex]["refresh"] = eventResilience

            elif lkey == "volumewarnpercentused" or lkey == "volumecriticalpercentused":
                for record in volumeRecords:
                    if record["space"].get("percent_used"):
                        if record["space"]["percent_used"] >= rule[key]:
                            uniqueIdentifier = record["uuid"] + "_" + key
                            eventIndex = eventExist(events, uniqueIdentifier)
                            if eventIndex < 0:
                                alertType = 'Warning' if lkey == "volumewarnpercentused" else 'Critical'
                                message = f'Volume Usage {alertType} Alert: volume {record["svm"]["name"]}:{record["name"]} on {clusterName} is {record["space"]["percent_used"]}% full, which is more or equal to {rule[key]}% full.'
                                sendAlert(message, "WARNING")
                                changedEvents = True
                                event = {
                                        "index": uniqueIdentifier,
                                        "message": message,
                                        "refresh": eventResilience
                                    }
                                events.append(event)
                            else:
                                # If the event was found, reset the refresh count. If it is just one less
                                # than the max, then it means it was decremented above so there wasn't
                                # really a change in state.
                                if events[eventIndex]["refresh"] != (eventResilience - 1):
                                    changedEvents = True
                                events[eventIndex]["refresh"] = eventResilience

            elif lkey == "volumewarnfilespercentused" or lkey == "volumecriticalfilespercentused":
                for record in volumeRecords:
                    #
                    # If a volume is offline, the API will not report the "files" information.
                    if record.get("files") is not None:
                        maxFiles = record["files"].get("maximum")
                        usedFiles = record["files"].get("used")
                        if maxFiles != None and usedFiles != None:
                            percentUsed = (usedFiles / maxFiles) * 100
                            if percentUsed >= rule[key]:
                                uniqueIdentifier = record["uuid"] + "_" + key
                                eventIndex = eventExist(events, uniqueIdentifier)
                                if eventIndex < 0:
                                    alertType = 'Warning' if lkey == "volumewarnfilespercentused" else 'Critical'
                                    message = f"Volume File (inode) Usage {alertType} Alert: volume {record['svm']['name']}:{record['name']} on {clusterName} is using {percentUsed:.0f}% of it's inodes, which is more or equal to {rule[key]}% utilization."
                                    sendAlert(message, "WARNING")
                                    changedEvents = True
                                    event = {
                                            "index": uniqueIdentifier,
                                            "message": message,
                                            "refresh": eventResilience
                                        }
                                    events.append(event)
                                else:
                                    # If the event was found, reset the refresh count. If it is just one less
                                    # than the max, then it means it was decremented above so there wasn't
                                    # really a change in state.
                                    if events[eventIndex]["refresh"] != (eventResilience - 1):
                                        changedEvents = True
                                    events[eventIndex]["refresh"] = eventResilience

            elif lkey == "offline":
                for record in volumeRecords:
                    if rule[key] and record["state"].lower() == "offline":
                        uniqueIdentifier = f'{record["uuid"]}_{key}_{rule[key]}'
                        eventIndex = eventExist(events, uniqueIdentifier)
                        if eventIndex < 0:
                            message = f"Volume Offline Alert: volume {record['svm']['name']}:{record['name']} on {clusterName} is offline."
                            sendAlert(message, "WARNING")
                            changedEvents=True
                            event = {
                                "index": uniqueIdentifier,
                                "message": message,
                                "refresh": eventResilience
                            }
                            events.append(event)
                        else:
                            # If the event was found, reset the refresh count. If it is just one less
                            # than the max, then it means it was decremented above so there wasn't
                            # really a change in state.
                            if events[eventIndex]["refresh"] != (eventResilience - 1):
                                changedEvents = True
                            events[eventIndex]["refresh"] = eventResilience
            elif lkey == "oldsnapshot":
                curTime = datetime.datetime.now(pytz.timezone(clusterTimezone) if clusterTimezone != None else datetime.timezone.utc)
                curTimeSec = curTime.timestamp()
                #
                # Run the API call to get the snapshot information.
                snapshotRecords = []
                for volume in volumeRecords:
                    if volume["flexcache_endpoint_type"].lower() != "cache" and volume["style"].lower() != "flexgroup_constituent":
                        url = f'/api/storage/volumes/{volume["uuid"]}/snapshots?fields=create_time,volume,svm&return_timeout=15'
                        while url is not None:
                            endpoint = f'https://{config["OntapAdminServer"]}{url}'
                            response = http.request('GET', endpoint, headers=headers)
                            if response.status != 200:
                                logger.error(f'API call to {endpoint} failed. HTTP status code {response.status}.')
                                break
                            else:
                                data = json.loads(response.data)
                                snapshotRecords.extend(data.get("records"))
                                if data.get("_links") is not None and data["_links"].get("next") is not None and data["_links"]["next"].get("href") is not None:
                                    url = data["_links"]["next"]["href"]
                                else:
                                    url = None
                logger.info(f'Found {len(snapshotRecords)} snapshots on cluster {clusterName}.')
                for snapshot in snapshotRecords:
                    if snapshot.get("create_time") is not None:
                        #
                        # Format should be: 2025-11-07T10:05:00-06:00
                        creationTime = datetime.datetime.strptime(snapshot["create_time"], '%Y-%m-%dT%H:%M:%S%z')
                        creationTimeSec = creationTime.timestamp()
                        ageSeconds = int(curTimeSec - creationTimeSec)
                        if ageSeconds >= (rule[key] * 60 * 60 * 24):
                            uniqueIdentifier = f'{snapshot["uuid"]}_{key}'
                            eventIndex = eventExist(events, uniqueIdentifier)
                            if eventIndex < 0:
                                timeStr = lagTimeStr(int(ageSeconds))
                                message = f'Old Snapshot Alert: snapshot {snapshot["name"]} on volume {snapshot["volume"]["name"]} in SVM {snapshot["svm"]["name"]} is {int(ageSeconds)} seconds old ({timeStr}), which is more than {rule[key]} days.'
                                sendAlert(message, "WARNING")
                                changedEvents=True
                                event = {
                                    "index": uniqueIdentifier,
                                    "message": message,
                                    "refresh": eventResilience
                                }
                                events.append(event)
                            else:
                                # If the event was found, reset the refresh count. If it is just one less
                                # than the max, then it means it was decremented above so there wasn't
                                # really a change in state.
                                if events[eventIndex]["refresh"] != (eventResilience - 1):
                                    changedEvents = True
                                events[eventIndex]["refresh"] = eventResilience
            else:
                message = f'Unknown storage alert type: "{key}" found for cluster {clusterName}.'
                logger.warning(message)
    #
    # After processing the records, see if any events need to be removed.
    i = len(events) - 1
    while i >= 0:
        if events[i]["refresh"] <= 0:
            logger.debug(f'Deleting event: {events[i]["message"]} on cluster {clusterName}')
            del events[i]
            changedEvents = True
        else:
            # If an event wasn't refreshed, then we need to save the new refresh count.
            if events[i]["refresh"] != eventResilience:
                changedEvents = True
        i -= 1
    #
    # If the events array changed, save it.
    if(changedEvents):
        s3Client.put_object(Key=config["storageEventsFilename"], Bucket=config["s3BucketName"], Body=json.dumps(events).encode('UTF-8'))

################################################################################
# This function sends the alert to a webhook defined by the
# config['webhookEndpoint'] variable. It is currently designed to work with a
# specific Moogsoft webhook implementation. You will most likely want to
# modify it to work with the destination you want to send the alert to.
################################################################################
def sendWebHook(message, severity):
    global clusterName, http, snsClient, config, logger

    if config.get('webhookEndpoint') is None:
        return
    #
    # Since the Moogsoft endpoint needs just the hostname for the configurationItem
    # strip off the account information that might have been added.
    x = clusterName.find("(")
    if x != -1:
        hostname = clusterName[0:x]
    else:
        hostname = clusterName
    #
    # The INC__identifier field needs to be unique for each message, so add
    # a hash of the message to it.
    messageHash = int(hashlib.sha256(message.encode("utf-8")).hexdigest(), 16) % (10 ** 8)
    payload = {
        "INC__summary": f"{severity}: FSx ONTAP Monitoring Services Alert for cluster {clusterName}",
        "INC__manager": "FSxONTAP",
        "INC__severity": "3",
        "INC__identifier": f"FSx ONTAP Monitoring Services alert for cluster {clusterName} - {messageHash}",
        "INC__configurationItem": hostname,
        "INC__fullMessageText": message
    }
    data = json.dumps(payload).encode('UTF-8')
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    #
    # Note that the urllib3 library that AWS natively provides for their Lambda functions
    # is of the 1.* version, so we have to use the syntax for that version.
    try:
        response = http.request('POST', config['webhookEndpoint'], headers=headers, body=data, timeout=5)
        if response.status == 200:
            logger.info(f"Webhook sent successfully for {clusterName}.")
        else:
            logger.error(f"Error: Received a non-200 HTTP status code when sending the webhook. HTTP response code received: {response.status}. The data in the response: {response.data}. This was on the behalf of cluster {clusterName}.")
    except (urllib3.exceptions.ConnectTimeoutError, urllib3.exceptions.MaxRetryError):
        message = f"Error: Exception occurred when sending to webhook {config['webhookEndpoint']} for cluster {clusterName}."
        logger.critical(message)
        subject = f'CRITICAL: Monitor ONTAP Services failed to send the webhook for cluster {clusterName}'
        snsClient.publish(TopicArn=config["snsTopicArn"], Message=message, Subject=subject[:100])

################################################################################
# This function converts a severity string to a number value.
################################################################################
def severityToNumber(severity):
    lseverity = severity.lower()
    if lseverity == "critical":
        return 1
    elif lseverity == "error":
        return 2
    elif lseverity == "warning":
        return 3
    elif lseverity == "info":
        return 4
    elif lseverity == "debug":
        return 5
    else:
        return 4

################################################################################
# This function sends the message to the various alerting systems.
################################################################################
def sendAlert(message, severity):
    global config, snsClient, logger, cloudWatchClient, clusterName, lambdaFunction

    #
    # Log to syslog, or the console if syslog isn't configured.
    if severity == "CRITICAL":
        logger.critical(message)
    elif severity == "ERROR":
        logger.error(message)
    elif severity == "WARNING":
        logger.warning(message)
    elif severity == "INFO":
        logger.info(message)
    elif severity == "DEBUG":
        logger.debug(message)
    else:
        logger.info(message)
    #
    # Publish to SNS.
    if lambdaFunction:
        source = " Lambda "
    else:
        source = " "
    #
    # Ensure the subject is less than 100 characters.
    subject = f'{severity}:{source}Monitor ONTAP Services Alert for cluster {clusterName}'
    snsClient.publish(TopicArn=config["snsTopicArn"], Message=message, Subject=subject[:100])
    #
    # Send to CloudWatch if defined.
    if cloudWatchClient is not None:
        #
        # Create a new log stream for the current day if it doesn't exist.
        dateStr = datetime.datetime.now().strftime("%Y-%m-%d")
        logStreamName = f'{clusterName}-monitor-ontap-services-{dateStr}'
        #
        # Don't ask me why AWS puts a ":*" at the end of the log group ARN, but they do.
        logGroupName = config["cloudWatchLogGroupArn"].split(":")[-2] if config["cloudWatchLogGroupArn"].endswith(":*") else config["cloudWatchLogGroupArn"].split(":")[-1]
        #
        # Check to see if the log stream already exists.
        try:
            logStreams = cloudWatchClient.describe_log_streams(logGroupName=logGroupName, logStreamNamePrefix=logStreamName)
            if len(logStreams["logStreams"]) == 0:
                cloudWatchClient.create_log_stream(logGroupName=logGroupName, logStreamName=logStreamName)
            #
            # Send the message to CloudWatch.
            cloudWatchClient.put_log_events(
                logGroupName=logGroupName,
                logStreamName=logStreamName,
                logEvents=[
                    {
                        'timestamp': int(datetime.datetime.now().timestamp() * 1000),
                        'message': message
                    }
                ]
            )
        except cloudWatchClient.exceptions.ResourceNotFoundException:
            logger.error(f'CloudWatch log group {logGroupName} not found for cluster {clusterName}.')
    #
    # Send to webhook if defined.
    if config.get('webhookEndpoint') is not None and severityToNumber(config['webhookSeverity']) >= severityToNumber(severity):
        sendWebHook(message, severity)

################################################################################
# This function is used to check utilization of quota limits.
################################################################################
def processQuotaUtilization(service):
    global config, s3Client, snsClient, http, headers, clusterName, clusterVersion, logger

    changedEvents=False
    #
    # Get the saved events so we can ensure we are only reporting on new ones.
    try:
        data = s3Client.get_object(Key=config["quotaEventsFilename"], Bucket=config["s3BucketName"])
    except botocore.exceptions.ClientError as err:
        # If the error is that the object doesn't exist, then it will get created once an alert it sent.
        if err.response['Error']['Code'] == "NoSuchKey":
            events = []
        else:
            raise Exception(err)
    else:
        events = json.loads(data["Body"].read().decode('UTF-8'))
    #
    # Decrement the refresh field to know if any records have really gone away.
    for event in events:
        event["refresh"] -= 1
    #
    # Run the API call to get the quota report.
    # For some reason the API version of the quota report became unrelable (i.e. returning 0 records)
    # so using the private CLI version of the API.
    #url = '/api/storage/quota/reports?fields=*&return_timeout=15'
    url = '/api/private/cli/volume/quota/report?fields=vserver,volume,index,tree,quota-type,quota-target,disk-used,disk-limit,files-used,file-limit,soft-disk-limit,soft-file-limit,quota-specifier,disk-used-pct-soft-disk-limit,disk-used-pct-disk-limit,files-used-pct-soft-file-limit,files-used-pct-file-limit&return_timeout=15'
    records = []
    while url is not None:
        endpoint = f'https://{config["OntapAdminServer"]}{url}'
        response = http.request('GET', endpoint, headers=headers)
        if response.status == 200:
            data = json.loads(response.data)
            records.extend(data.get("records"))
        else:
            logger.error(f'API call to {endpoint} failed. HTTP status code: {response.status}.')
            return
        if data.get("_links") is not None and data["_links"].get("next") is not None and data["_links"]["next"].get("href") is not None:
            url = data["_links"]["next"]["href"]
        else:
            url = None

    logger.info(f'Found {len(records)} quota report records cluster={clusterName}.')
    for record in records:
        for rule in service["rules"]:
            for key in rule.keys():
                lkey = key.lower() # Convert to all lower case so the key can be case insensitive.
                if lkey == "maxsoftquotainodespercentused":
                    if(record.get("files_used_pct_soft_file_limit") is not None and record["files_used_pct_soft_file_limit"] >= rule[key]):
                        uniqueIdentifier = str(record["index"]) + "_" + key
                        eventIndex = eventExist(events, uniqueIdentifier)
                        if eventIndex < 0:
                            userStr = ''
                            qtreeStr = ' '
                            if record["quota_type"] == "user":
                                users = None
                                for user in record["quota_target"]:
                                    if users is None:
                                        users = user
                                    else:
                                        users += f',{user}'
                                userStr=f'associated with user(s) "{users}" '
                            if record.get("tree") is not None:
                                qtreeStr=f' under qtree: {record["tree"]} '
                            message = f'Quota Inode Usage Alert: Soft quota of type "{record["quota_type"]}" on {record["vserver"]}:/{record["volume"]}{qtreeStr}{userStr}on {clusterName} is using {record["files_used_pct_soft_file_limit"]}% which is more than {rule[key]}% of its inodes.'
                            sendAlert(message, "WARNING")
                            changedEvents=True
                            event = {
                                    "index": uniqueIdentifier,
                                    "message": message,
                                    "refresh": eventResilience
                                    }
                            events.append(event)
                        else:
                            # If the event was found, reset the refresh count. If it is just one less
                            # than the max, then it means it was decremented above so there wasn't
                            # really a change in state.
                            if events[eventIndex]["refresh"] != (eventResilience - 1):
                                changedEvents = True
                            events[eventIndex]["refresh"] = eventResilience

                elif lkey == "maxquotainodespercentused" or lkey == "maxhardquotainodespercentused":
                    if(record.get("files_used_pct_file_limit") is not None and record["files_used_pct_file_limit"] >= rule[key]):
                        uniqueIdentifier = str(record["index"]) + "_" + key
                        eventIndex = eventExist(events, uniqueIdentifier)
                        if eventIndex < 0:
                            userStr = ''
                            qtreeStr = ' '
                            if record["quota_type"] == "user":
                                users = None
                                for user in record["quota_target"]:
                                    if users is None:
                                        users = user
                                    else:
                                        users += f',{user}'
                                userStr=f'associated with user(s) "{users}" '
                            if record.get("tree") is not None:
                                qtreeStr=f' under qtree: {record["tree"]} '
                            message = f'Quota Inode Usage Alert: Hard quota of type "{record["quota_type"]}" on {record["vserver"]}:/{record["volume"]}{qtreeStr}{userStr}on {clusterName} is using {record["files_used_pct_file_limit"]}% which is more than {rule[key]}% of its inodes.'
                            sendAlert(message, "WARNING")
                            changedEvents=True
                            event = {
                                    "index": uniqueIdentifier,
                                    "message": message,
                                    "refresh": eventResilience
                                    }
                            events.append(event)
                        else:
                            # If the event was found, reset the refresh count. If it is just one less
                            # than the max, then it means it was decremented above so there wasn't
                            # really a change in state.
                            if events[eventIndex]["refresh"] != (eventResilience - 1):
                                changedEvents = True
                            events[eventIndex]["refresh"] = eventResilience

                elif lkey == "maxhardquotaspacepercentused":
                    if(record.get("disk_used_pct_disk_limit") and record["disk_used_pct_disk_limit"] >= rule[key]):
                        uniqueIdentifier = str(record["index"]) + "_" + key
                        eventIndex = eventExist(events, uniqueIdentifier)
                        if eventIndex < 0:
                            userStr = ''
                            qtreeStr = ' '
                            if record["quota_type"] == "user":
                                users = None
                                for user in record["quota_target"]:
                                    if users is None:
                                        users = user
                                    else:
                                        users += f',{user}'
                                userStr=f'associated with user(s) "{users}" '
                            if record.get("tree") is not None:
                                qtreeStr=f' under qtree: {record["tree"]} '
                            message = f'Quota Space Usage Alert: Hard quota of type "{record["quota_type"]}" on {record["vserver"]}:/{record["volume"]}{qtreeStr}{userStr}on {clusterName} is using {record["disk_used_pct_disk_limit"]}% which is more than {rule[key]}% of its allocated space.'
                            sendAlert(message, "WARNING")
                            changedEvents=True
                            event = {
                                    "index": uniqueIdentifier,
                                    "message": message,
                                    "refresh": eventResilience
                                    }
                            events.append(event)
                        else:
                            # If the event was found, reset the refresh count. If it is just one less
                            # than the max, then it means it was decremented above so there wasn't
                            # really a change in state.
                            if events[eventIndex]["refresh"] != (eventResilience - 1):
                                changedEvents = True
                            events[eventIndex]["refresh"] = eventResilience

                elif lkey == "maxsoftquotaspacepercentused":
                    if(record.get("disk_used_pct_soft_disk_limit") and record["disk_used_pct_soft_disk_limit"] >= rule[key]):
                        uniqueIdentifier = str(record["index"]) + "_" + key
                        eventIndex = eventExist(events, uniqueIdentifier)
                        if eventIndex < 0:
                            userStr = ''
                            qtreeStr = ' '
                            if record["quota_type"] == "user":
                                users = None
                                for user in record["quota_target"]:
                                    if users is None:
                                        users = user
                                    else:
                                        users += f',{user}'
                                userStr=f'associated with user(s) "{users}" '
                            if record.get("tree") is not None:
                                qtreeStr=f' under qtree: {record["tree"]} '
                            message = f'Quota Space Usage Alert: Soft quota of type "{record["quota_type"]}" on {record["vserver"]}:/{record["volume"]}{qtreeStr}{userStr}on {clusterName} is using {record["disk_used_pct_soft_disk_limit"]}% which is more than {rule[key]}% of its allocated space.'
                            sendAlert(message, "WARNING")
                            changedEvents=True
                            event = {
                                "index": uniqueIdentifier,
                                "message": message,
                                "refresh": eventResilience
                            }
                            events.append(event)
                        else:
                            # If the event was found, reset the refresh count. If it is just one less
                            # than the max, then it means it was decremented above so there wasn't
                            # really a change in state.
                            if events[eventIndex]["refresh"] != (eventResilience - 1):
                                changedEvents = True
                            events[eventIndex]["refresh"] = eventResilience

                else:
                    message = f'Unknown quota matching condition type "{key}" found for cluster {clusterName}.'
                    logger.warning(message)
    #
    # After processing the records, see if any events need to be removed.
    i = len(events) - 1
    while i >= 0:
        if events[i]["refresh"] <= 0:
            logger.debug(f'Deleting event: {events[i]["message"]} Cluster={clusterName}')
            del events[i]
            changedEvents = True
        else:
            # If an event wasn't refreshed, then we need to save the new refresh count.
            if events[i]["refresh"] != eventResilience:
                changedEvents = True
        i -= 1
    #
    # If the events array changed, save it.
    if(changedEvents):
        s3Client.put_object(Key=config["quotaEventsFilename"], Bucket=config["s3BucketName"], Body=json.dumps(events).encode('UTF-8'))

################################################################################
################################################################################
def processVserver(service):
    global config, s3Client, snsClient, http, headers, clusterName, logger

    changedEvents=False
    #
    # Get the saved events so we can ensure we are only reporting on new ones.
    try:
        data = s3Client.get_object(Key=config["vserverEventsFilename"], Bucket=config["s3BucketName"])
    except botocore.exceptions.ClientError as err:
        # If the error is that the object doesn't exist, then it will get created once an alert it sent.
        if err.response['Error']['Code'] == "NoSuchKey":
            events = []
        else:
            raise Exception(err)
    else:
        events = json.loads(data["Body"].read().decode('UTF-8'))
    #
    # Decrement the refresh field to know if any records have really gone away.
    for event in events:
        event["refresh"] -= 1
    #
    # Consolidate the rules
    vserverState = None
    nfsProtocolState = None
    cifsProtocolState = None
    for rule in service["rules"]:
        for key in rule.keys():
            lkey = key.lower() # Convert to all lower case so the key can be case insensitive.
            if lkey == "vserverstate":
                vserverState = rule[key]
                vserverStateKey = key
            elif lkey == "nfsprotocolstate":
                nfsProtocolState = rule[key]
                nfsProtocolStateKey = key
            elif lkey == "cifsprotocolstate":
                cifsProtocolState = rule[key]
                cifsProtocolStateKey = key
    #
    # Check for any vservers that are down.
    if vserverState is not None and vserverState:
        #
        # Run the API call to get the vserver state for each vserver.
        url = f'/api/svm/svms?fields=state&return_timeout=15'
        records = []
        while url is not None:
            endpoint = f'https://{config["OntapAdminServer"]}{url}'
            response = http.request('GET', endpoint, headers=headers)
            if response.status == 200:
                data = json.loads(response.data)
                records.extend(data.get("records"))
            else:
                logger.error(f'API call to {endpoint} failed. HTTP status code {response.status}.')
                break

            if data.get("_links") is not None and data["_links"].get("next") is not None and data["_links"]["next"].get("href") is not None:
                url = data["_links"]["next"]["href"]
            else:
                url = None

        logger.info(f'Found {len(records)} vservers to check on cluster {clusterName}.')
        for record in records:
            if record["state"].lower() != "running":
                uniqueIdentifier = str(record["uuid"]) + "_" + vserverStateKey
                eventIndex = eventExist(events, uniqueIdentifier)
                if eventIndex < 0:
                    message = f'SVM State Alert: SVM {record["name"]} on {clusterName} is not online.'
                    sendAlert(message, "WARNING")
                    changedEvents=True
                    event = {
                            "index": uniqueIdentifier,
                            "message": message,
                            "refresh": eventResilience
                            }
                    events.append(event)
                else:
                    # If the event was found, reset the refresh count. If it is just one less
                    # than the max, then it means it was decremented above so there wasn't
                    # really a change in state.
                    if events[eventIndex]["refresh"] != (eventResilience - 1):
                        changedEvents = True
                    events[eventIndex]["refresh"] = eventResilience

    if nfsProtocolState is not None and nfsProtocolState:
        #
        # Run the API call to get the NFS protocol state for each vserver.
        url = '/api/protocols/nfs/services?fields=state&return_timeout=15'
        records = []
        while url is not None:
            endpoint = f'https://{config["OntapAdminServer"]}{url}'
            response = http.request('GET', endpoint, headers=headers)
            if response.status == 200:
                data = json.loads(response.data)
                records.extend(data.get("records"))
            else:
                logger.error(f'API call to {endpoint} failed. HTTP status code {response.status}.')
                break
            if data.get("_links") is not None and data["_links"].get("next") is not None and data["_links"]["next"].get("href") is not None:
                url = data["_links"]["next"]["href"]
            else:
                url = None

        for record in records:
            if record["state"].lower() != "online":
                uniqueIdentifier = str(record["svm"]["uuid"]) + "_" + nfsProtocolStateKey
                eventIndex = eventExist(events, uniqueIdentifier)
                if eventIndex < 0:
                    message = f'NFS Protocol State Alert: NFS protocol on {record["svm"]["name"]} on {clusterName} is not online.'
                    sendAlert(message, "WARNING")
                    changedEvents=True
                    event = {
                            "index": uniqueIdentifier,
                            "message": message,
                            "refresh": eventResilience
                            }
                    events.append(event)
                else:
                    # If the event was found, reset the refresh count. If it is just one less
                    # than the max, then it means it was decremented above so there wasn't
                    # really a change in state.
                    if events[eventIndex]["refresh"] != (eventResilience - 1):
                        changedEvents = True
                    events[eventIndex]["refresh"] = eventResilience

    if cifsProtocolState is not None and cifsProtocolState:
        #
        # Run the API call to get the NFS protocol state for each vserver.
        url = '/api/protocols/cifs/services?fields=enabled&return_timeout=15'
        records = []
        while url is not None:
            endpoint = f'https://{config["OntapAdminServer"]}{url}'
            response = http.request('GET', endpoint, headers=headers)
            if response.status == 200:
                data = json.loads(response.data)
                records.extend(data.get("records"))
            else:
                logger.error(f'API call to {endpoint} failed. HTTP status code {response.status}.')
                break
            if data.get("_links") is not None and data["_links"].get("next") is not None and data["_links"]["next"].get("href") is not None:
                url = data["_links"]["next"]["href"]
            else:
                url = None

        for record in records:
            if not record["enabled"]:
                uniqueIdentifier = str(record["svm"]["uuid"]) + "_" + cifsProtocolStateKey
                eventIndex = eventExist(events, uniqueIdentifier)
                if eventIndex < 0:
                    message = f'CIFS Protocol State Alert: CIFS protocol on {record["svm"]["name"]} on {clusterName} is not online.'
                    sendAlert(message, "WARNING")
                    changedEvents=True
                    event = {
                            "index": uniqueIdentifier,
                            "message": message,
                            "refresh": eventResilience
                            }
                    events.append(event)
                else:
                    # If the event was found, reset the refresh count. If it is just one less
                    # than the max, then it means it was decremented above so there wasn't
                    # really a change in state.
                    if events[eventIndex]["refresh"] != (eventResilience - 1):
                        changedEvents = True
                    events[eventIndex]["refresh"] = eventResilience

    #
    # After processing the records, see if any events need to be removed.
    i = len(events) - 1
    while i >= 0:
        if events[i]["refresh"] <= 0:
            logger.debug(f'Deleting event: {events[i]["message"]} for cluster {clusterName}')
            del events[i]
            changedEvents = True
        else:
            # If an event wasn't refreshed, then we need to save the new refresh count.
            if events[i]["refresh"] != eventResilience:
                changedEvents = True
        i -= 1
    #
    # If the events array changed, save it.
    if(changedEvents):
        s3Client.put_object(Key=config["vserverEventsFilename"], Bucket=config["s3BucketName"], Body=json.dumps(events).encode('UTF-8'))

################################################################################
# This function returns the index of the service in the conditions dictionary.
################################################################################
def getServiceIndex(targetService, conditions):

    i = 0
    while i < len(conditions["services"]):
        if conditions["services"][i]["name"] == targetService:
            return i
        i += 1

    return None

################################################################################
# This function builds a default matching conditions dictionary based on the
# environment variables passed in.
################################################################################
def buildDefaultMatchingConditions(event):
    #
    # Define global variables so we don't have to pass them to all the functions.
    global config, s3Client, snsClient, http, headers, clusterName, clusterVersion, logger
    #
    # Define an empty matching conditions dictionary.
    conditions = { "services": [
        {"name": "systemHealth", "rules": []},
        {"name": "ems", "rules": []},
        {"name": "snapmirror", "rules": []},
        {"name": "storage", "rules": []},
        {"name": "quota", "rules": []},
        {"name": "vserver", "rules": []}
    ]}
    #
    # Now, add rules based on the environment variables.
    for name, value in event.items() if event.get('OntapAdminServer') is not None else os.environ.items():
        if name == "initialVersionChangeAlert":
            if value == "true":
                conditions["services"][getServiceIndex("systemHealth", conditions)]["rules"].append({"versionChange": True})
            else:
                conditions["services"][getServiceIndex("systemHealth", conditions)]["rules"].append({"versionChange": False})
        elif name == "initialFailoverAlert":
            if value == "true":
                conditions["services"][getServiceIndex("systemHealth", conditions)]["rules"].append({"failover": True})
            else:
                conditions["services"][getServiceIndex("systemHealth", conditions)]["rules"].append({"failover": False})
        elif name == "initialNetworkInterfacesAlert":
            if value == "true":
                conditions["services"][getServiceIndex("systemHealth", conditions)]["rules"].append({"networkInterfaces": True})
            else:
                conditions["services"][getServiceIndex("systemHealth", conditions)]["rules"].append({"networkInterfaces": False})
        elif name == "initialEmsEventsAlert":
            if value == "true":
                conditions["services"][getServiceIndex("ems", conditions)]["rules"].append({"name": "", "severity": "error|alert|emergency", "message": "", "filter": ""})
        elif name == "initialSnapMirrorHealthAlert":
            if value == "true":
                conditions["services"][getServiceIndex("snapmirror", conditions)]["rules"].append({"Healthy": False})  # This is what it matches on, so it is interesting when the health is false.
            else:
                conditions["services"][getServiceIndex("snapmirror", conditions)]["rules"].append({"Healthy": True})
        elif name == "initialSnapMirrorLagTimeAlert":
            value = int(value)
            if value > 0:
                conditions["services"][getServiceIndex("snapmirror", conditions)]["rules"].append({"maxLagTime": value})
        elif name == "initialSnapMirrorLagTimePercentAlert":
            value = int(value)
            if value > 0:
                conditions["services"][getServiceIndex("snapmirror", conditions)]["rules"].append({"maxLagTimePercent": value})
        elif name == "initialSnapMirrorStalledAlert":
            value = int(value)
            if value > 0:
                conditions["services"][getServiceIndex("snapmirror", conditions)]["rules"].append({"stalledTransferSeconds": value})
        elif name == "initialFileSystemUtilizationWarnAlert":
            value = int(value)
            if value > 0:
                conditions["services"][getServiceIndex("storage", conditions)]["rules"].append({"aggrWarnPercentUsed": value})
        elif name == "initialFileSystemUtilizationCriticalAlert":
            value = int(value)
            if value > 0:
                conditions["services"][getServiceIndex("storage", conditions)]["rules"].append({"aggrCriticalPercentUsed": value})
        elif name == "initialVolumeUtilizationWarnAlert":
            value = int(value)
            if value > 0:
                conditions["services"][getServiceIndex("storage", conditions)]["rules"].append({"volumeWarnPercentUsed": value})
        elif name == "initialVolumeUtilizationCriticalAlert":
            value = int(value)
            if value > 0:
                conditions["services"][getServiceIndex("storage", conditions)]["rules"].append({"volumeCriticalPercentUsed": value})
        elif name == "initialVolumeFileUtilizationWarnAlert":
            value = int(value)
            if value > 0:
                conditions["services"][getServiceIndex("storage", conditions)]["rules"].append({"volumeWarnFilesPercentUsed": value})
        elif name == "initialVolumeFileUtilizationCriticalAlert":
            value = int(value)
            if value > 0:
                conditions["services"][getServiceIndex("storage", conditions)]["rules"].append({"volumeCriticalFilesPercentUsed": value})
        elif name == "initialVolumeOfflineAlert":
            if value == "true":
                conditions["services"][getServiceIndex("storage", conditions)]["rules"].append({"offline": True})
            else:
                conditions["services"][getServiceIndex("storage", conditions)]["rules"].append({"offline": False})
        elif name == "initialOldSnapshot":
            value = int(value)
            if value > 0:
                conditions["services"][getServiceIndex("storage", conditions)]["rules"].append({"oldSnapshot": value})
        elif name == "initialSoftQuotaUtilizationAlert":
            value = int(value)
            if value > 0:
                conditions["services"][getServiceIndex("quota", conditions)]["rules"].append({"maxSoftQuotaSpacePercentUsed": value})
        elif name == "initialHardQuotaUtilizationAlert":
            value = int(value)
            if value > 0:
                conditions["services"][getServiceIndex("quota", conditions)]["rules"].append({"maxHardQuotaSpacePercentUsed": value})
        elif name == "initialInodesSoftQuotaUtilizationAlert":
            value = int(value)
            if value > 0:
                conditions["services"][getServiceIndex("quota", conditions)]["rules"].append({"maxSoftQuotaInodesPercentUsed": value})
        elif name == "initialInodesQuotaUtilizationAlert":
            value = int(value)
            if value > 0:
                conditions["services"][getServiceIndex("quota", conditions)]["rules"].append({"maxHardQuotaInodesPercentUsed": value})
        elif name == "initialVserverStateAlert":
            if value == "true":
                conditions["services"][getServiceIndex("vserver", conditions)]["rules"].append({"vserverState": True})
            else:
                conditions["services"][getServiceIndex("vserver", conditions)]["rules"].append({"vserverState": False})
        elif name == "initialVserverNFSProtocolStateAlert":
            if value == "true":
                conditions["services"][getServiceIndex("vserver", conditions)]["rules"].append({"nfsProtocolState": True})
            else:
                conditions["services"][getServiceIndex("vserver", conditions)]["rules"].append({"nfsProtocolState": False})
        elif name == "initialVserverCIFSProtocolStateAlert":
            if value == "true":
                conditions["services"][getServiceIndex("vserver", conditions)]["rules"].append({"cifsProtocolState": True})
            else:
                conditions["services"][getServiceIndex("vserver", conditions)]["rules"].append({"cifsProtocolState": False})

    return conditions

################################################################################
# This function is used to read in all the configuration parameters from the
# various places:
#   Lambda Event
#   Environment Variables
#   Config File
#   Calculated
################################################################################
def readInConfig(event):
    #
    # Define global variables so we don't have to pass them to all the functions.
    global config, s3Client, snsClient, http, headers, logger, clusterName
    #
    # Define a dictionary with all the required variables so we can
    # easily add them and check for their existence.
    requiredEnvVariables = {
        "OntapAdminServer": None,
        "s3BucketName": None,
        "s3BucketRegion": None
        }

    optionalVariables = {
        "configFilename": None,
        "secretsManagerEndPointHostname": None,
        "snsEndPointHostname": None,
        "cloudWatchLogsEndPointHostname": None,
        "syslogIP": None,
        "cloudWatchLogGroupArn": None,
        "awsAccountId": None,
        "webhookEndpoint": None,
        "webhookSeverity": "INFO",
        "secretUsernameKey": None,
        "secretPasswordKey": None
        }

    filenameVariables = {
        "emsEventsFilename": None,
        "smEventsFilename": None,
        "smRelationshipsFilename": None,
        "conditionsFilename": None,
        "storageEventsFilename": None,
        "quotaEventsFilename": None,
        "systemStatusFilename": None,
        "vserverEventsFilename": None
        }

    config = {
        "snsTopicArn": None,
        "secretArn": None
        }
    config.update(filenameVariables)
    config.update(optionalVariables)
    config.update(requiredEnvVariables)
    #
    # Get the required, and any additional, paramaters from the environment or event.
    logger.debug("Being called from a Lambda function." if event.get('OntapAdminServer') is not None else "Being called from a timer or standalone.")
    for var in config:
        config[var] = event.get(var) if event.get('OntapAdminServer') is not None else os.environ.get(var)
    #
    # Since the CloudFormation template will set the environment variables
    # to an empty string if someone doesn't provide a value, reset the
    # values back to None.
    for var in config:
        if config[var] == "":
            config[var] = None
    #
    # Since CloudFormation has to pass an ARN, get the Bucket name from it.
    # Too bad the bucket ARN doesn't include the region, like most (all?) the others do.
    if config["s3BucketName"] is None and os.environ.get("s3BucketArn") is not None:
        config["s3BucketName"] = os.environ.get("s3BucketArn").split(":")[-1]
    #
    # Check that required environmental variables are there.
    for var in requiredEnvVariables:
        if config[var] is None:
            raise Exception (f'\n\nMissing required environment variable "{var}".')
    #
    # At this point we an set the clusterName to the OntapAdminServer value. It will
    # be overwritten in the "checkSystem()" function.
    clusterName = config["OntapAdminServer"]
    #
    # Open a client to the s3 service.
    s3Client = boto3.client('s3', config["s3BucketRegion"])
    #
    # Calculate the config filename if it hasn't already been provided.
    defaultConfigFilename = config["OntapAdminServer"] + "-config"
    if config["configFilename"] is None:
        config["configFilename"] = defaultConfigFilename
    #
    # Process the config file if it exist.
    try:
        lines = s3Client.get_object(Key=config["configFilename"], Bucket=config["s3BucketName"])['Body'].iter_lines()
    except botocore.exceptions.ClientError as err:
        if err.response['Error']['Code'] != "NoSuchKey":
            raise Exception(err)
        else:
            if config["configFilename"] != defaultConfigFilename:
                logger.warning(f"Warning, did not find file '{config['configFilename']}' in s3 bucket '{config['s3BucketName']}' in region '{config['s3BucketRegion']}' for cluster {clusterName}.")
    else:
        #
        # While iterating through the file, get rid of any "export ", comments, blank lines, or anything else that isn't key=value.
        for line in lines:
            line = line.decode('utf-8')
            if line[0:7] == "export ":
                line = line[7:]
            comment = line.split("#")
            line=comment[0].strip().replace('"', '')
            x = line.split("=")
            if len(x) == 2:
                (key, value) = line.split("=")
            key = key.strip()
            value = value.strip()
            if len(value) == 0:
                logger.warning(f"Warning, empty value for key '{key}' on cluster {clusterName} .")
            else:
                #
                # Preserve any environment variables settings.
                if key in config:
                    if config[key] is None:
                        config[key] = value
                else:
                    logger.warning(f"Warning, unknown config parameter '{key}' found on cluster {clusterName}.")
    #
    # Now, fill in the filenames for any that aren't already defined.
    for filename in filenameVariables:
        if config[filename] is None:
            config[filename] = config["OntapAdminServer"] + "-" + filename.replace("Filename", "")
    #
    # Define endpoints if alternates weren't provided.
    if config.get("secretArn") is not None and config["secretsManagerEndPointHostname"] is None:
        secretRegion = config["secretArn"].split(":")[3]
        config["secretsManagerEndPointHostname"] = f'secretsmanager.{secretRegion}.amazonaws.com'

    if config.get("snsTopicArn") is not None and config["snsEndPointHostname"] is None:
        snsRegion = config["snsTopicArn"].split(":")[3]
        config["snsEndPointHostname"] = f'sns.{snsRegion}.amazonaws.com'

    if config.get("cloudWatchLogGroupArn") is not None and config["cloudWatchLogsEndPointHostname"] is None:
        cloudWatchRegion = config["cloudWatchLogGroupArn"].split(":")[3]
        config["cloudWatchLogsEndPointHostname"] = f'logs.{cloudWatchRegion}.amazonaws.com'

    if config.get("secretPasswordKey") is None:
        config["secretPasswordKey"] = "password"

    if config.get("secretUsernameKey") is None:
        config["secretUsernameKey"] = "username"
    #
    # Now, check that all the configuration parameters have been set.
    for key in config:
        if config[key] is None and key not in optionalVariables:
            raise Exception(f'\n\nMissing configuration parameter "{key}".\n\n')

################################################################################
# Main logic
################################################################################
def lambda_handler(event, context):
    #
    # Define global variables so we don't have to pass them to all the functions.
    global config, s3Client, snsClient, http, headers, clusterName, clusterVersion, logger, cloudWatchClient, clusterTimezone
    #
    # Set up logging.
    logging.basicConfig()
    logger = logging.getLogger("MOS_Monitoring")
    if lambdaFunction:
        logger.setLevel(logging.INFO)       # Anything at this level and above this get logged.
    else: # Assume we are running in a test environment.
        logger.setLevel(logging.DEBUG)      # Anything at this level and above this get logged.
        formatter = logging.Formatter(
                fmt="%(name)s:%(funcName)s - Level:%(levelname)s - Message:%(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
        loggerscreen = logging.StreamHandler()
        loggerscreen.setFormatter(formatter)
        logger.addHandler(loggerscreen)
    #
    # Read in the configuraiton.
    readInConfig(event)   # This defines the s3Client variable.
    #
    # Set up the logger to log to a file and to syslog.
    if config["syslogIP"] is not None:
        #
        # Due to a bug with the SysLogHandler() of not sending proper framing with a message
        # when using TCP (it should end it with a LF and not a NUL like it does now) you must add
        # an additional frame delimiter to the receiving syslog server. With rsyslog, you add
        # a AddtlFrameDelimiter="0" directive to the "input()" line where they have it listen
        # to a TCP port. For example:
        #
        #  # provides TCP syslog reception
        #  module(load="imtcp")
        #  input(type="imtcp" port="514" AddtlFrameDelimiter="0")
        #
        # Because of this bug, I am going to stick with UDP, the default protocol used by
        # the syslog handler. If TCP is required, then the above changes will have to be made
        # to the syslog server. Or, the program will have to handle closing and opening the
        # connection for each message. The following will do that:
        #    handler.flush()
        #    handler.close()
        #    logger.removeHandler(handler)
        #    handler = logging.handlers.SysLogHandler(facility=SysLogHandler.LOG_LOCAL0, address=(syslogIP, 514), socktype=socket.SOCK_STREAM)
        #    handler.setFormatter(formatter)
        #    logger.addHandler(handler)
        #
        # You might get away with a simple handler.open() after the close(), without having to
        # remove and add the handler. I didn't test that.
        handler = logging.handlers.SysLogHandler(facility=SysLogHandler.LOG_LOCAL0, address=(config["syslogIP"], 514))
        formatter = logging.Formatter(
                fmt="%(name)s:%(funcName)s - Level:%(levelname)s - Message:%(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    #
    # Create a Secrets Manager client.
    session = boto3.session.Session()
    secretRegion = config["secretArn"].split(":")[3]
    client = session.client(service_name='secretsmanager', region_name=secretRegion, endpoint_url=f'https://{config["secretsManagerEndPointHostname"]}')
    #
    # Get the username and password of the ONTAP/FSxN system.
    secretsInfo = client.get_secret_value(SecretId=config["secretArn"])
    secrets = json.loads(secretsInfo['SecretString'])
    if secrets.get(config['secretUsernameKey']) is None:
        logger.critical(f'Error, "{config["secretUsernameKey"]}" not found in secret "{config["secretArn"]}" for cluster {config["OntapAdminServer"]}.')
        return

    if secrets.get(config['secretPasswordKey']) is None:
        logger.critical(f'Error, "{config["secretPasswordKey"]}" not found in secret "{config["secretArn"]}" for cluster {config["OntapAdminServer"]}.')
        return

    username = secrets[config['secretUsernameKey']]
    password = secrets[config['secretPasswordKey']]
    #
    # Create clients to the other AWS services we will be using.
    #s3Client = boto3.client('s3', config["s3BucketRegion"])  # Defined in readInConfig()
    snsRegion = config["snsTopicArn"].split(":")[3]
    snsClient = boto3.client('sns', region_name=snsRegion, endpoint_url=f'https://{config["snsEndPointHostname"]}')
    cloudWatchClient = None
    if config["cloudWatchLogGroupArn"] is not None:
        cloudWatchRegion = config["cloudWatchLogGroupArn"].split(":")[3]
        cloudWatchClient = boto3.client('logs', region_name=cloudWatchRegion, endpoint_url=f'https://{config["cloudWatchLogsEndPointHostname"]}')
    #
    # Create a http handle to make ONTAP/FSxN API calls with.
    auth = urllib3.make_headers(basic_auth=f'{username}:{password}')
    headers = { **auth }
    #
    # Disable warning about connecting to servers with self-signed SSL certificates.
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    retries = Retry(total=None, connect=1, read=1, redirect=10, status=0, other=0)  # pylint: disable=E1123
    http = urllib3.PoolManager(cert_reqs='CERT_NONE', retries=retries)
    #
    # Get the conditions we know what to alert on.
    try:
        data = s3Client.get_object(Key=config["conditionsFilename"], Bucket=config["s3BucketName"])
        matchingConditions = json.loads(data["Body"].read().decode('UTF-8'))
    except botocore.exceptions.ClientError as err:
        if err.response['Error']['Code'] != "NoSuchKey":
            logger.error(f'Error, could not retrieve configuration file {config["conditionsFilename"]} from: s3://{config["s3BucketName"]} for cluster {config["OntapAdminServer"]}.\nBelow is additional information:')
            raise Exception(err)
        else:
            matchingConditions = buildDefaultMatchingConditions(event)
            s3Client.put_object(Key=config["conditionsFilename"], Bucket=config["s3BucketName"], Body=json.dumps(matchingConditions, indent=4).encode('UTF-8'))
    except json.decoder.JSONDecodeError as err:
        logger.error(f'Error, could not decode JSON from configuration file "{config["conditionsFilename"]}" for cluster {config["OntapAdminServer"]}. The error message from the decoder:\n{err}\n')
        return

    if(checkSystem()):
        #
        # Loop on all the configured ONTAP services we want to check on.
        for service in matchingConditions["services"]:
            if service["name"].lower() == "systemhealth":
                checkSystemHealth(service)
            elif service["name"].lower() == "ems":
                processEMSEvents(service)
            elif (service["name"].lower() == "snapmirror"):
                processSnapMirrorRelationships(service)
            elif service["name"].lower() == "storage":
                processStorageUtilization(service)
            elif service["name"].lower() == "quota":
                processQuotaUtilization(service)
            elif service["name"].lower() == "vserver":
                processVserver(service)
            else:
                logger.warning(f'Unknown service "{service["name"]}" found for cluster {clusterName}.')
    return

if os.environ.get('AWS_LAMBDA_FUNCTION_NAME') is None:
    lambdaFunction = False
    lambda_handler(None, None)
else:
    lambdaFunction = True
