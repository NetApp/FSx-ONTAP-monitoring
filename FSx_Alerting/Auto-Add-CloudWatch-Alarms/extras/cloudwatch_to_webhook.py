################################################################################
# This program is designed to be used as an AWS Lambda function that is
# triggered by an FSx volume utilization AWS CloudWatch alarm created by the
# Auto-Add-CloudWatch-Alarm program found here:
#
#   https://github.com/NetApp/FSx-ONTAP-monitoring/tree/main/FSx_Alerting/Auto-Add-CloudWatch-Alarms
#
# When the alarm is triggered, it will send a webhook to a endpoint
# with the details about the alarm.
#
# The endpoint to send the webhook to is defined by the 'webhookEndpoint'
# environment variable. The payload of the webhook is defined by the
# 'payloadTemplate' environment variable. The program will make the following
# substitutions to the payload template before sending the webhook:
#   {volume_id} -> The ID of the FSxN volume that is breaching the threshold.
#   {filesystem_id} -> The ID of the FSxN file system that is breaching the
#                      threshold.
#   {threshold} -> The threshold that is being breached.
#   {utilization} -> The current utilization of the FSxN file system that is
#                    breaching the threshold.
#
# The program uses the urllib3 library to send the HTTP POST request to the
# webhook endpoint.
################################################################################
import os
import json
import urllib3
#
# This function sends the webhook.
def sendWebhook(volume_id, filesystem_id, threshold, utilization):
    #
    # Get the payloadTemplate and endpoint from the environment variables.
    payload = os.environ.get("payloadTemplate", f"Alert! Volume {volume_id} in file system {filesystem_id} has breached utilization threshold {threshold}%. Current utilization is {utilization}%.")
    webhookEndpoint = os.environ.get("webhookEndpoint", "")
    #
    # If webhookEndpoint is not set, raise an exception since we can't send the webhook without an endpoint.
    if webhookEndpoint == "":
        raise Exception("Error: No webhook endpoint found in environment variables. Please set the 'webhookEndpoint' environment variable to the URL you want to send the webhook to.")
    #
    # Replace the fields in the payload.
    for fieldName in ["volume_id", "filesystem_id", "threshold", "utilization"]:
        payload = payload.replace("{" + fieldName + "}", str(locals()[fieldName]))

    data = json.dumps(payload).encode('UTF-8')
    webhookHeaders = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    #
    # Note that the urllib3 library that AWS natively provides for their Lambda functions
    # is of the 1.* version, so we have to use the syntax for that version.
    try:
        print(f'Sending webhook to {webhookEndpoint} with these headers {webhookHeaders} and the following data: {data}')
        response = http.request('POST', webhookEndpoint, headers=webhookHeaders, body=data, timeout=5)
        if response.status == 200:
            print("Webhook sent successfully.")
        else:
            print(f"Error: Received a non-200 HTTP status code when sending the webhook. HTTP response code received: {response.status}. The data in the response: {response.data}.")
    except (urllib3.exceptions.ConnectTimeoutError, urllib3.exceptions.MaxRetryError):
        print(f"Error: Exception occurred when sending to webhook {webhookEndpoint}.")

################################################################################
# This is effectively the function that CloudWatch will call when it triggers.
# The 'event' parameter will contain all the information about the alarm.
# The following is very specific to the CloudWatch alarm that is created by
# the Auto-Add-CloudWatch-Alarm program.
################################################################################
def lambda_handler(event, context):
    if event["source"] == "aws.cloudwatch" and event["alarmData"]["state"]["value"] == "ALARM":
        for metric in event["alarmData"]["configuration"]["metrics"]:
            if metric.get("metricStat") is not None:
                if metric["metricStat"].get("metric") is not None:
                    if metric["metricStat"]["metric"]["name"] == "StorageUsed":
                        volId=metric["metricStat"]["metric"]["dimensions"].get("VolumeId")
                        fsId=metric["metricStat"]["metric"]["dimensions"].get("FileSystemId")
                        reason = json.loads(event["alarmData"]["state"]["reasonData"])
                        utilization = reason["recentDatapoints"][0]
                        threshold = reason["threshold"]
                        print(f"Alert! Volume {volId} in file system {fsId} has breached utilization threshold {threshold}%. Current utilization is {utilization}%.")
                        sendWebhook(volId, fsId, threshold, utilization)
#
# Define the handle to send HTTP request with.
http = urllib3.PoolManager()
