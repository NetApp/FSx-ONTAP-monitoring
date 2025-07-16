# Ingest FSx for ONTAP administrative audit logs into CloudWatch

## Overview
This sample demonstrates a way to ingest the administrative audit logs from an FSx for Data ONTAP file system into a CloudWatch log group.
It will attempt to gather the administrative logs from all the FSx for Data ONTAP file systems that are within a specified region.
It will skip any file systems where the credentials aren't provided.
It will maintain a "stats" file in an S3 bucket that will keep track of the last time it successfully ingested the administrative logs from each
FSx for ONTAP file system to ensure it doesn't add duplicate entries to the CloudWatch log group.
You can run this script as a standalone program or as a Lambda function. These directions assume you are going to run it as a Lambda function.

**NOTE**: There are two ways to install this program. Either with the [CloudFormation script](cloudformation-template.yaml) found this this repo,
or by following the manual instructions found in the [README-MANUAL.md](README-MANUAL.md) file.

## Prerequisites
- An FSx for Data ONTAP file system.
- An S3 bucket.
    - A "stats" file that is maintained by the program will be stored in this bucket. It is used to keep track of the last time the Lambda function successfully
    ingested administrative logs from each of the FSx for ONTAP file systems. Its size will be small (i.e. less than a few megabytes).
    - Optionally, a file that contains the ARNs of the Secrets Manager secrets that contain the credentials for the FSx for ONTAP file systems you want to ingest the administrative logs from.
- A CloudWatch log group to ingest the administrative logs into. Each file system will get a different log stream within the log group everyday.
- An AWS Secrets Manager secret for each of the FSx for ONTAP file systems you wish to ingest the administrative logs from. The secret should have two keys `username` and `password`. For example:
    ```json
      {
        "username": "fsxadmin",
        "password": "superSecretPassword"
      }
    ```
    - If you use want to use the same credentials for all the FSx for ONTAP file systems, then you can specify a default secret ARN with the `defaultSecretARN` parameter.

**You can either create the following items before running the CloudFormation script, or allow it to create the items for you.**

- AWS Endpoints. Since the Lambda function runs within your VPC it will have restrictions as to how it can access the Internet.
It will not be able to access the Internet from a "Public" subnet (i.e. one that has a Internet gateway attached it it.) It will, however,
be able to access the Internet through a Transit or a NAT gateway. So, if the subnets you plan to run this Lambda function from
don't have a Transit or NAT gateway then there needs to be an VPC AWS service endpoint for all the AWS services that this Lambda function uses.
Specifically, the Lambda function needs to be able to access the following AWS services:
  - FSx.
  - Secrets Manager.
  - CloudWatch Logs.
  - S3 - Note that typically there is a Gateway type VPC endpoint for S3, therefore you typically you don't need to create a VPC endpoint for S3.

   **NOTE**: That if you specify to have the CloudFormation template create an endpoint and one already exist, it will cause the CloudFormation script to fail.

- Role for the Lambda function. Create a role with the necessary permissions to allow the Lambda function to do the following:

<!--- Using HTML to create a table that has rowspan attributes since the markdown table syntax does not support that. --->
<table>
<tr><th>Service</td><th>Actions</td><th>Resources</th></tr>
<tr><td>Fsx</td><td>fsx:DescribeFileSystems</td><td>&#42;</td></tr>
<tr><td rowspan="3">ec2</td><td>DescribeNetworkInterfaces</td><td>&#42;</td></tr>
<tr><td>CreateNetworkInterface</td><td rowspan="2">arn:aws:ec2:&lt;region&gt;:&lt;accountID&gt;:&#42;</td></tr>
<tr><td>DeleteNetworkInterface</td></tr>
<tr><td rowspan="3">CloudWatch Logs</td><td>CreateLogGroup</td><td rowspan="3">arn:aws:logs:&lt;region&gt;:&lt;accountID&gt;:log-group:&#42;</td></tr>
<tr><td>CreateLogStream</td></tr>
<tr><td>PutLogEvents</td></tr>
<tr><td rowspan="3">s3</td><td> ListBucket</td><td> arn:aws:s3:&lt;region&gt;:&lt;accountID&gt;:&#42;</td></tr>
<tr><td>GetObject</td><td rowspan="2">arn:aws:s3:&lt;region>:&lt;accountID&gt;:&#42;/&#42;</td></tr>
<tr><td>PutObject</td></tr>
<tr><td>Secrets Manager</td><td> GetSecretValue </td><td>arn:aws:secretsmanager:&lt;region&gt;:&lt;accountID&gt;:secret:&lt;secretName&gt&#42;</td></tr>
</table>
Where:

- &lt;accountID&gt; -  is your AWS account ID.
- &lt;region&gt; - is the region where the FSx for ONTAP file systems are located.
- &lt;secretName&gt; - is the name of the secret that contains the credentials for the fsxadmin accounts. **Note** that this
resource string, through the use of wild card characters, must include all the secrets that the Lambda function will access.
Or you must list each secret ARN individually.

Notes:
- Since the Lambda function runs within your VPC it needs to be able to create and delete network interfaces.
- The AWS Security Group Policy builder incorrectly generates resource lines for the `CreateNetworkInterface`
and `DeleteNetworkInterface` actions. The correct resource line is `arn:aws:ec2:<region>:<accountID>:*`.
- It needs to be able to create a log groups so it can create a log group for the diagnostic output from the Lambda function.
- Since the ARN of any Secrets Manager secret has random characters at the end of it, you must add the `*` at the end, or provide the full ARN of the secret.

## Deployment
1. Download the [cloudformation-template.yaml](cloudformation-template.yaml) file from this repository.
1. Make sure you are in the region where you want to capture the administrative logs from.
1. Go to the CloudFormation page within the AWS console. Make sure you are in the region where you want to capture the administrative logs from.
1. Click on the `Create stack -> With new resources` button.
1. Select the `Upload a template file` radio button and click on the `Choose file` button. Select the `cloudformation-template.yaml` that you downloaded in step 1.
1. Click on the `Next` button.
1. The next page will provide all the configuration parameters you can provide:

    |Parameter|Required|Description|
    |---|---|--|
    |Stack Name|Yes|The name of the CloudFormation stack. This can be anything, but since it is used as a suffix for some of the resources it creates, keep it under 40 characters.|
    |checkInterval|Yes|The interval in minutes that the Lambda function will check for new audit logs. Default is 5 minutes |
    |logGroupName|Yes|The name of the CloudWatch log group to ingest the audit logs into. This should have already been created based on your business requirements.|
    |subNetIds|Yes|Select the subnets that you want the Lambda function to run in. Any subnet selected must have connectivity to all the FSxN file system management endpoints that you want to gather audit logs from.|
    |lambdaSecruityGroupsIds|Yes|Select the security groups that you want the Lambda function associated with. The security group must allow outbound traffic on TCP port 443. Inbound rules don't matter since the Lambda function is not accessible from a network.|
    |s3BucketName|Yes|The name of the S3 bucket where the stats file is stored. This bucket must already exist.|
    |s3BucketRegion|Yes|The region of the S3 bucket resides.|
    |createWatchdogAlarm|No|If set to `true` it will create a CloudWatch alarm that will alert you if the Lambda function throws in error.|
    |snsTopicArn|No|The ARN of the SNS topic to send the alarm to. This is required if `createWatchdogAlarm` is set to `true`.|
    |inputFilter|No|If provided, this will be treated as a regular expression and matched against the `input` field of a log event. Any event that matches will not stored into the CloudWatch LogStream. If not provided, all events will be stored.|
    |inputMatch|No|If provided, this will be treated as a regular expression and matched against the `input` field of a log event. If an event that matches it will be stored into the CloudWatch LogStream. If it doesn't match, the event will not be stored into the CloudWatch LogStream. If not provided, all events will be stored.|
    |applicationMatch|No|If provided, this will be treated as a regular expression and matched against the `application` field of a log event. If an event that matches it will be stored into the CloudWatch LogStream. If it doesn't match, the event will not be stored into the CloudWatch LogStream. If not provided, all events will be stored.|
    |userMatch|No|If provided, this will be treated as a regular expression and matched against the `user` field of a log event. If an event that matches it will be stored into the CloudWatch LogStream. If it doesn't match, the event will not be stored into the CloudWatch LogStream. If not provided, all events will be stored.|
    |stateMatch|No|If provided, this will be treated as a regular expression and matched against the `state` field of a log event. If an event that matches it will be stored into the CloudWatch LogStream. If it doesn't match, the event will not be stored into the CloudWatch LogStream. If not provided, all events will be stored.|
    |fsxnSecretARNsFile|No|The name of a file within the S3 bucket that contains the Secret ARNs for each for the FSxN file systems. The format of the file should have one line for each file system where it specifies the file system id, an equal sign, and then the Secret ARN to use. For example: `fs-0e8d9172fa5411111=arn:aws:secretsmanager:us-east-1:123456789012:secret:fsxadmin-abc123`|
    |defaultSecretARN|No|The ARN of a Secrets Manager secret that contains the credentials for an FSx for ONTAP account. Not recommended to use the 'fsxadmin' user. This secrect will be used if a specific ARN is not provided for a file system. **CAUTION** Repeated failed API calls dut to bad credentials could lock out an account.|
    |fileSystem1ID|No|The ID of the first FSxN file system to ingest the audit logs from.|
    |fileSystem1SecretARN|No|The ARN of the secret that contains the credentials for the first FSx for Data ONTAP file system.|
    |fileSystem2ID|No|The ID of the second FSx for Data ONTAP file system to ingest the audit logs from.|
    |fileSystem2SecretARN|No|The ARN of the secret that contains the credentials for the second FSx for Data ONTAP file system.|
    |fileSystem3ID|No|The ID of the third FSx for Data ONTAP file system to ingest the audit logs from.|
    |fileSystem3SecretARN|No|The ARN of the secret that contains the credentials for the third FSx for Data ONTAP file system.|
    |fileSystem4ID|No|The ID of the forth FSx for Data ONTAP file system to ingest the audit logs from.|
    |fileSystem4SecretARN|No|The ARN of the secret that contains the credentials for the forth FSx for Data ONTAP file system.|
    |fileSystem5ID|No|The ID of the fifth FSx for Data ONTAP file system to ingest the audit logs from.|
    |fileSystem5SecretARN|No|The ARN of the secret that contains the credentials for the fifth FSx for Data ONTAP file system.|
    |lambdaRoleArn|No|The ARN of the role that the Lambda function will use. If not provided, the CloudFormation script will create a role for you.|
    |schedulerRoleArn|No|The ARN of the role that the EventBridge scheduler will run as. If not provided, the CloudFormation script will create a role for you.|
    |createFsxEndpoint|No|If set to `true` it will create the VPC endpoints for the FSx service|
    |createCloudWatchLogsEndpoint|No|If set to `true` it will create the VPC endpoints for the CloudWatch Logs service|
    |createSecretsManagerEndpoint|No|If set to `true` it will create the VPC endpoints for the Secrets Manager service|
    |createS3Endpoint|No|If set to `true` it will create the VPC endpoints for the S3 service|
    |routeTableIds|No|If creating an S3 gateway endpoint, these are the routing tables you want updated to use the endpoint.|
    |vpcId|No|This is the VPC that the endpoint(s) will be created in. Only needed if you are creating an endpoint.|
    |endpointSecurityGroupIds|No|The security group that the endpoint(s) will be associated with. Must allow incoming TCP traffic over port 443. Only needed if you are creating an endpoint.|

    **Note**: You must either provide the fsxnSecretARNsFile, defaultSecretARN or the fileSystem1ID, fileSystem1SecretARN, fileSystem2ID, fileSystem2SecretARN, etc. parameters.

6. Click on the `Next` button.
7. The next page will provide for some additional configuration options. You can leave these as the default values.
At the bottom of the page, there is a checkbox that you must check to allow the CloudFormation script to create the
necessary IAM roles and policies. Note that if you have provided the ARNs to the two required roles, then the
CloudFormation script will not create any roles.
8. Click on the `Next` button.
9. The next page will provide a summary of the configuration you have provided. Review it to ensure it is correct.
10. Click on the `Create stack` button.

## After deployment tasks
### Confirm that the Lambda function is ingesting administrative logs.
After the CloudFormation deployment has completed, go to the "resource" tab of the CloudFormation stack and click on the Lambda function hyperlink.
This will take you to the Lambda function's page.
Click on the Monitoring sub tab and then click on "View CloudWatch logs". This will take you to the CloudWatch log group where the Lambda function
writes its diagnostic output to. You should see a log stream. If you don't, wait a few minutes, and then refresh the page. If you still don't
see a log stream, check the Lambda function's configuration to ensure it is correct. Once a log stream appears, click on it to see the diagnostic
output from the Lambda function. You should see log messages indicating that it is ingesting audit logs. If you see any "Errors" then you will
need to investigate and correct the issue. If you can't figure it out, please open an [issue](https://github.com/NetApp/FSx-ONTAP-monitoring/issues) in this repository.

### Add more FSx for ONTAP file systems.
The way the program is written, it will automatically discover all FSxN file systems within a region,
So, if you add another FSxN it will automatically attempt to ingest the administrative logs from it.
Unfortunately, it won't be able to, until you provide a Secret ARN for that file system.

The best way to add a secret ARN, is to either update the secretARNs file you
initially passed to the CloudFormation script, that should be in the S3 bucket you specified in
the `s3BucketName` parameter, or create that file with the information for all the FSxN file systems
you want to ingest the audit logs from and then store it in the S3 bucket. See the description
of the `fsxnSecretARNsFile` parameter above for the format of the file.

If you are creating the file for the first time, you'll also need to set the `fsxSecretARNsFile` environment variable
to point to the file. You can leave all the other parameters as they are, including the `fileSystem1ID`, `fileSystem1SecretARN`, etc. ones as
the program will ignore those parameters if the `fsxnSecretARNsFile` environment variable is set. To set
the environment variable, go to the Lambda function's configuration page and click on the "Configuration" tab. Then
click on the "Environment variables" sub tab. Click on the "Edit" button. The `fsxnSecretARNsFile`
environment variable should already be there, but the value should be blank. If the variable isn't there click on the
'add' button and add it. Once the line is there with the `fsxnSecretARNsFile` variable, set the value
to the name of the file you created.

## Author Information

This repository is maintained by the contributors listed on [GitHub](https://github.com/NetApp/FSx-ONTAP-monitoring/graphs/contributors).

## License

Licensed under the Apache License, Version 2.0 (the "License").

You may obtain a copy of the License at [apache.org/licenses/LICENSE-2.0](http://www.apache.org/licenses/LICENSE-2.0).

Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an _"AS IS"_ basis, without WARRANTIES or conditions of any kind, either express or implied.

See the License for the specific language governing permissions and limitations under the License.

© 2025 NetApp, Inc. All Rights Reserved.
