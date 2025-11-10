# FSx ONTAP CloudWatch Monitoring Stack

## Overview
This section of the repository contains a CloudFormation template that creates a comprehensive monitoring
solution for AWS FSx for NetApp ONTAP file systems.

It provides real-time visibility into performance, capacity, and operational health through native AWS
CloudWatch services with automated data collection, custom dashboards, and intelligent alerting.

### Core Components
#### Lambda Function
Container-based serverless function that serves as the central data collection engine:
* Collects metrics from FSx ONTAP REST APIs
* Manages CloudWatch dashboards dynamically
* Processes and forwards EMS logs
* Creates and manages CloudWatch alarms
* 5-minute timeout, 256MB memory allocation

#### EventBridge Schedulers
Three automated schedules orchestrating different monitoring aspects:
* Metrics: Every 5 minutes - Performance data collection
* Dashboard: Every hour - Dashboard and alarm management
* EMS Logs: Configurable (1-1440 min) - Event log streaming

#### IAM Roles & Policies
Least-privilege security model with granular permissions:
* Lambda execution role with VPC access
* EventBridge Scheduler role for Lambda invocation
* FSx API access permissions
* CloudWatch metrics and logs write access
* Secrets Manager read access for credentials

### Deployment Modes
#### Full Stack Mode
"FSx Metrics, FSx Alerts, EMS Logs"
* Complete monitoring solution
* Performance metrics collection
* Automated alerting system
* Event Management System logs
* Comprehensive dashboard

#### Monitoring Only Mode
"FSx Metrics, FSx Alerts"
* Performance monitoring
* CloudWatch alarms
* Dashboard creation
* No EMS log collection
* Reduced resource usage

#### EMS Logs Only Mode
"FSx EMS Logs"
* Event log streaming only
* CloudWatch Logs integration
* Configurable collection interval
* No performance metrics
* Minimal infrastructure

### CloudWatch Dashbaord Section
| Section | Metrics Displayed | Purpose |
|-----------------|-------------------|---------|
| Client Operations | Read/Write/Metadata IOPS, Throughput (MiB/s) | Monitor client-side performance and activity|
| Storage Utilization | SSD tier usage, Capacity pool consumption | Track storage capacity and tiering efficiency |
| Disk Performance | Disk IOPS, Disk throughput, Backend operations |	Monitor underlying storage performance |
| Latency Metrics| Average response times for Read/Write/Metadata | Identify performance bottlenecks |
| Volume-Level Stats | Per-volume IOPS, throughput, capacity utilization | Granular volume performance monitoring |
| LUN Performance | iSCSI LUN IOPS, throughput, latency | Block storage protocol monitoring |
| SnapMirror Status | Replication relationship health | Data protection monitoring |
| Alarm Overview | Active alarms, alarm states, categories | Centralized alert management |

### Automation and Scheduling
#### Metrics Collction (Every 5 Minutes)
* Performance metrics collection
* ONTAP API data retrieval
* Custom metric publishing
* Real-time dashboard updates

#### Dashboard Management (Every Hour)
* Dashboard definition updates
* Alarm creation and modification
* Threshold adjustments
* Resource optimization

#### EMS Log Collection (Configurable Interval)
* ONTAP event message retrieval
* Log filtering and formatting
* CloudWatch Logs integration
* Retention policy management

## Implementation
Depending on which deployment mode you select, the Cloudformation template will create the following resources:

| Resource | Full stack | Monitoring only | EMS logs only | Description |
|----------|------------|-----------------|---------------|-------------
| Dashboard | Yes | Yes | No |  The Amazon CloudWatch dashboard |
| Lambda function | Yes | Yes | Yes | The service does the following:<br>Build custom widgets for the dashboard.<br>Collect metrics directly from ONTAP (like SnapMirror health status and EMS messages).<br>Create CloudWatch alarms for all files systems in the region.|
| Schedulers | Yes | Yes | Yes | Three Amazon EventBridge schedulers that trigger the Lambda function to:<br>Collect ONTAP metrics.<br>Create, update or delete CloudWatch alarms.<br>Cellect EMS messages|
| CloudWatch alarm | Yes | Yes | Yes | This alarm will alert you if the Lambda function fails. Not created if you don't provide an SNS Topic to send alerts to.|
| Lambda Role | Yes | Yes | Yes | The IAM role that allows the Lambda function to run. This is optional if you don't provide a role ARN for the Lambda function to use.|
| Scheduler Role | Yes | Yes | Yes | The IAM role that allows the scheduler to trigger the Lambda function. This is optinoal if you don't provide a role ARN for the scheduler to use. |
| SecretManager endpoint | Yes | Yes | Yes | This allows the Lambda function to access the SecretManager API. It is optional and only needed if the Lamdba function is deployed into a "Public" subnet. |
| CloudWatch endpoint | Yes | Yes | Yes | This allows the Lambda function to access the CloudWatch API. It is optional and only needed if the Lamdba function is deployed into a "Public" subnet. |
| FSxService endpoint | Yes | Yes | Yes | This allows the Lambda function to access the FSxService API. It is optional and only needed if the Lamdba function is deployed into a "Public" subnet. |
| CloudWatch Logs endpoint | Yes | No | Yes | This allows the Lambda function to access the CloudWatch Logs API. It is optional and only needed if the Lamdba function is deployed into a "Public" subnet. |

## Prerequisites
1. You should have an AWS Account with the following permissions to create and manage resources:
    * "cloudformation:DescribeStacks"
    * "cloudformation:ListStacks"
    * "cloudformation:DescribeStackEvents"
    * "cloudformation:ListStackResources"
    * "cloudformation:CreateChangeSet"
    * "ec2:DescribeSubnets"
    * "ec2:DescribeSecurityGroups"
    * "ec2:DescribeVpcs"
    * "iam:ListRoles"
    * "iam:GetRolePolicy"
    * "iam:GetRole"
    * "iam:DeleteRolePolicy"
    * "iam:CreateRole"
    * "iam:DetachRolePolicy"
    * "iam:PassRole"
    * "iam:PutRolePolicy"
    * "iam:DeleteRole"
    * "iam:AttachRolePolicy"
    * "lambda:AddPermission"
    * "lambda:RemovePermission"
    * "lambda:InvokeFunction"
    * "lambda:GetFunction"
    * "lambda:CreateFunction"
    * "lambda:DeleteFunction"
    * "lambda:TagResource"
    * "codestar-connections:GetSyncConfiguration"
    * "ecr:BatchGetImage"
    * "ecr:GetDownloadUrlForLayer"
    * "scheduler:GetSchedule"
    * "scheduler:CreateSchedule"
    * "scheduler:DeleteSchedule"
    * "logs:PutRetentionPolicy"
    * "secretsmanager:GetSecretValue" (on specific secret)
2. Optional: create a secret in AWS Secrets Manager with key-value pairs of file system IDs and their corresponding credentials value.  
Value can be provided in two formats. The first format is simply the password for the 'fsxadmin' user. The second format includes both the username and password, separated by a colon.
This secret is necessary for making direct ONTAP API calls to monitor resources, such as SnapMirror relations.
Examples secret structure:
```
    {
        "fs-111222333": "Password1",
        "fs-444555666": "Password2"
    }
    or 
    {
        "fs-111222333": "myUserName:Password1",
        "fs-444555666": "Password2"
    }	
```
When deploying the CloudFormation template, you will need to provide the ARN of this secret as a parameter. This allows the Lambda function to securely access the passwords for monitoring purposes.
Note: If you choose not to provide this secret, some monitoring capabilities (such as SnapMirror relations metrics) may be limited.

## Usage
To use this solution, you will need to run the CloudFormation template in your AWS account.
The CloudFormation template requires the following parameters:

1. Stack name - Identifier for the CloudFormation stack. Must not exceed 25 characters. (Note: While AWS allows stack names up to 
128 characters, limit yours to 25. This name is used as base name for other resource names created within the stack, so keeping it short prevents issues with other resource names getting too long.)
2. VPC ID - The ID of the VPC in which the Lambda function will run. This VPC must have connectivity to all target file systems. It 
can be either the same VPC where the file systems are located, or a different VPC with established connectivity (e.g. VPC peering, Transit Gateway) to the file systems' VPCs.
3. Subnet IDs - The IDs of the subnets in which the Lambda function will run. These subnets must have connectivity to the file 		
systems.
4. Security Group IDs - The IDs of the Security Groups that will be associated with the Lambda function when it runs. These Security 
Groups must allow connectivity to the file systems.
5. Create FSx Service Endpoint - A boolean flag indicating whether you plan to create a FSxService VPC endpoint inside the VPC. Set 
this to true if you want to create the endpoint, or false if you don't. The decision to create this endpoint depends on whether you already have this type of endpoint in the subnet where the Lambda function is to run. If you already have one, set this to false; otherwise, set it to true.	
6. Create Secret Manager Endpoint - A boolean flag indicating whether you plan to create a SecretManager VPC endpoint inside the 
VPC. Set this to true if you want to create the endpoint, or false if you don't. The decision to create this endpoint depends on whether you already have this type of endpoint in the subnet where the Lambda function is to run. If you already have one, set this to false; otherwise, set it to true.
7. Create CloudWatch Endpoint - A boolean flag indicating whether you plan to create a CloudWatch VPC endpoint inside the VPC. Set 
this to true if you want to create the endpoint, or false if you don't. The decision to create this endpoint depends on whether you already have this type of endpoint in the subnet where the Lambda function is to run. If you already have one, set this to false; otherwise, set it to true.
8. Secret Manager FSx Admin Passwords ARN - Optional - The ARN of the AWS Secrets Manager secret containing the fsx credentials.
This ARN is required for certain functionalities, such as snapmirror metrics collection. 
If not provided, some features may not operate correctly. This secret should contain key-value pairs as described in Prerequisites section above.
9. SNS Topic ARN for CloudWatch alarms - Optional - The ARN of the SNS topic to which CloudWatch alarms will be sent. If not provided, alarms will not be notified to any SNS topic.

## Alarms Configuration
The Lambda function is responsible for creating alarms based on the thresholds set via environment variables. These environment variables can be set from the AWS console, under the Configuration tab of the dashboard Lambda function. You can find the specific Lambda function by its name “FSxNDashboard-<CloudFormation-Stack-Name>.
The following environment variables are used:
1. CLIENT_THROUGHPUT_ALARM_THRESHOLD: This sets the threshold for the client throughput alarm. The default value is "90", but this can be customized as needed. When the client throughput exceeds this value (expressed as a percentage), an alarm will be triggered.
1. DISK_PERFORMANCE_ALARM_THRESHOLD: This sets the threshold for the disk performance alarm. The default value is "90", but this can be customized as needed. When the disk performance exceeds this value (expressed as a percentage), an alarm will be triggered.
1. DISK_THROUGHPUT_UTILIZATION_ALARM_THRESHOLD: This sets the threshold for the disk throughput utilization alarm. The default value is "90", but this can be customized as needed. When disk throughput utilization exceeds this value (expressed as a percentage), an alarm will be triggered.
1. SNAPMIRROR_UNHEALTHY_ALARM_THRESHOLD: This sets the threshold for the SnapMirror unhealthy alarm. The default value is "0", but this can be customized as needed. When the number of unhealthy SnapMirror relationships exceeds this value, an alarm will be triggered.
1. STORAGE_CAPACITY_UTILIZATION_ALARM_THRESHOLD: This sets the threshold for the storage capacity utilization alarm. The default value is "80", but this can be customized as needed. When storage capacity utilization exceeds this value (expressed as a percentage), an alarm will be triggered.
1. VOLUME_STORAGE_CAPACITY_UTILIZATION_ALARM_THRESHOLD: This sets the threshold for the volume storage capacity utilization alarm. The default value is "80", but this can be customized as needed. When volume storage capacity utilization exceeds this value (expressed as a percentage), an alarm will be triggered.

In addition to the environment variables, you can use tags on the FSx and volume resources to override default thresholds or skip alarm management for specific resources. If a threshold is set to 100, the alarm will not be created. Similarly, skip tag is set to true, the alarm will be skipped.

The tag keys used for this purpose are:

1. client-throughput-alarm-threshold
1. skip-client-throughput-alarm
1. disk-performance-alarm-threshold
1. skip-disk-performance-alarm
1. disk-throughput-utilization-threshold
1. skip-disk-throughput-utilization-alarm
1. storage-capacity-utilization-alarm-threshold
1. skip-storage-capacity-utilization-alarm
1. volume-storage-capacity-utilization-alarm-threshold
1. skip-volume-storage-capacity-utilization-alarm
1. snapMirror-unhealthy-relations-alarm-threshold
1. skip-snapmirror-unhealthy-relations-alarm

## Important Disclaimer: CloudWatch Alarms Deletion
Please note that when you delete the CloudFormation stack associated with this project, the CloudWatch Alarms created by the stack will not be automatically deleted. 

CloudFormation does not manage the lifecycle of CloudWatch Alarms created by the Lambda function. This means that even after stack deletion, these alarms will persist in your AWS account.

To fully clean up resources after using this solution:
1. Delete the CloudFormation stack as usual.
2. Manually review and delete any associated CloudWatch Alarms through the AWS Console or using AWS CLI/SDK.
You can find the alarms by searching for the name prefix "FSx-ONTAP" in the CloudWatch Alarms section.

This behavior ensures that important monitoring setups are not unintentionally removed, but it requires additional steps for complete resource cleanup.

## Author Information

This repository is maintained by the contributors listed on [GitHub](https://github.com/NetApp/FSx-ONTAP-monitoring/graphs/contributors).

## License

Licensed under the Apache License, Version 2.0 (the "License").

You may obtain a copy of the License at [apache.org/licenses/LICENSE-2.0](http://www.apache.org/licenses/LICENSE-2.0).

Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" basis, without WARRANTIES or conditions of any kind, either express or implied.

See the License for the specific language governing permissions and limitations under the License.
