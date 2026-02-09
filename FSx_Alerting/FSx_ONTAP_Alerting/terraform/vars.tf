#
# These are the variables used by the Terraform configuration. You can set them
# in a terraform.tfvars file, or provide them as environment variables when
# running Terraform.
variable "region" {
  description = "The AWS region where you want the resources deployed."
  type        = string
}

variable "s3BucketName" {
    description = "The name of the S3 bucket to use to store the status and configuration files. Must also be holding the lambda_layer.zip file. Must be in the same region as the other resources."
    type        = string
}

variable "FSxNListFilename" {
  description = "The file (object) in the S3 bucket that contains the list of FSxNs to monitor. The format of the file is specified in the README file on the GitHub repo where this program is maintained."
  type        = string
  default     = "FSxNList"
}

variable "subNetIds" {
    description = "The subnet IDs where you want to deploy the Lambda function. Must have connectivity to the FSxN file system to be monitored. Recommended to have at least two. Also recommended to be in a private subnet."
    type        = list(string)
}

variable "securityGroupIds" {
    description = "The security group IDs to associate with the Lambda function. Must allow outbound traffic over TCP port 443 to the FSxN file systems you want to monitor, and the AWS service endpoints."
    type        = list(string)
}

variable "snsTopicArn" {
    description = "The ARN of the SNS topic where you want alerts sent to."
    type        = string
}

variable "secretArnPattern" {
    description = "The ARN pattern of the Secrets Manager secrets that holds the FSxN credentials to use. This is only needed if you are allowing Terraform to create the role for the monitoring Lambda function. Defaults to 'arn:aws:secretsmanager:*:*:secret:FSxSecret*'"
    type        = string
    default     = "arn:aws:secretsmanager:*:*:secret:FSxSecret*"
}

variable "checkInterval" {
    description = "The interval, in minutes, between checks."
    type        = number
    default     = 15
}

variable "createWatchdogAlarm" {
    description = "Create a CloudWatch alarm to monitor the controller and monitoring Lambda functions. It will alert you if the Lambda function fails to run successfully. Defaults to 'true'."
    type        = bool
    default     = true
}

variable "implementWatchdogAsLambda" {
    description = "Use a Lambda function to publish to the SNS topic so the topic can reside in a different region. Only needed if you are creating the CloudWatch alarm and the SNS topic is in a different region. Defaults to 'false'"
    type        = bool
    default     = false
}

variable "watchdogRoleArn" {
    description = "The ARN of the role to assign to the Lambda function that will publish messages to the SNS topic if the monitoring function doesn't run properly. This is only needed if you are having the CloudWatch alarm created, implemented as a Lambda function and you want to provide an existing role, otherwise, if needed, an appropriate role will be created for you."
    type        = string
    default     = ""
}

variable "controllerRoleArn" {
    description = "The ARN of the role to use for the controller Lambda function. This is only needed if you want to provide an existing role, otherwise an appropriate one will be created for you."
    type        = string
    default     = ""
}

variable "monitorRoleArn" {
    description = "The ARN of the role to use for the monitoring Lambda function. This is only needed if you want to provide an existing role, otherwise an appropriate one will be created for you."
    type        = string
    default     = ""
}

variable "lambdaLayerArn" {
    description = "The ARN of the Lambda Layer to use for the Lambda function. This is only needed if you want to use an existing Lambda layer, typically from a previous installation of this program. If no ARN is provided, a Lambda Layer will be created for you from the lambda_layer.zip found in your S3 bucket."
    type        = string
    default     = ""
}

variable "maxRunTime" {
    description = "The maximum time, in seconds, the monitoring Lambda function is allowed to run before being terminated. Must be between 60 and 900 seconds."
    type        = number
    default     = 60
    validation {
        condition     = var.maxRunTime >= 60 && var.maxRunTime <= 900
        error_message = "The maxRunTime variable must be between 60 and 900 seconds."
    }
}

variable "memorySize" {
    description = "The amount of memory to allocate to the monitoring Lambda function, in MB. Must be between 128 and 10240 MB. Note that higher memory also means more CPU resources."
    type        = number
    default     = 128
    validation {
        condition     = var.memorySize >= 128 && var.memorySize <= 10240
        error_message = "The memorySize variable must be between 128 and 10240 MB."
    }
}

variable "createSecretsManagerEndpoint" {
    description = "Set to 'true' if you want to create a Secrets Manager endpoint."
    type        = bool
    default     = false
}

variable "createSNSEndpoint" {
    description = "Set to 'true' if you want to create an SNS endpoint."
    type        = bool
    default     = false
}

variable "createCloudWatchLogsEndpoint" {
    description = "Set to 'true' if you want to create a CloudWatch logs endpoint."
    type        = bool
    default     = false
}

variable "createS3Endpoint" {
    description = "Set to 'true' if you want to create an S3 endpoint."
    type        = bool
    default     = false
}

variable "routeTableIds" {
    description = "The route table IDs, comma separated, to update to use the S3 endpoint. Since the S3 endpoint is of type 'Gateway' route tables have to be updated to use it. This parameter is only needed if createS3Endpoint is set to 'true'."
    type        = list(string)
    default     = []
}

variable "vpcId" {
    description = "The VPC ID where the FSxN file system is located. This is only needed if you are creating an endpoint."
    type        = string
    default     = ""
}

variable "endpointSecurityGroupIds" {
    description = "The security group IDs, comma separated list, to associate with the SNS, SecretsManager and/or CloudWatch Logs endpoints. Must allow inbound traffic from from the Lambda function over TCP port 443. This parameter is only needed if you are creating the SNS, SecretsManager, or CloudWatch Logs endpoint."
    type        = list(string)
    default     = []
}

variable "versionChangeAlert" {
    description = "Alert when the ONTAP version changes."
    type        = string
    default     = "true"
}

variable "failoverAlert" {
    description = "Alert when a failover occurs."
    type        = string
    default     = "true"
}

variable "emsEventsAlert" {
    description = "Alert for EMS messages."
    type        = string
    default     = "true"
}

variable "snapMirrorLagTimeAlert" {
    description = "Alert when a SnapMirror update time is more than the specified seconds. Set to 0 to disable this alert. Recommended to set both snapMirrorLagTimeAlert and snapMirrorLagTimePercentAlert."
    type        = number
    default     = 86400
}

variable "snapMirrorLagTimePercentAlert" {
    description = "Alert when the last succesful SnapMirror update time is more than this percent of the amount of time since the last scheduled update. Must be more than 100. A value of 200 means 2 times the update interval. Set to 0 to disable this alert."
    type        = number
    default     = 200
}

variable "snapMirrorStalledAlert" {
    description = "Alert when a SnapMirror update hasn't transferred any new data in the specified seconds. Set to 0 to disable this alert."
    type        = number
    default     = 600
}

variable "snapMirrorHealthAlert" {
    description = "Alert when the SnapMirror relationship is not healthy."
    type        = string
    default     = "true"
}

variable "fileSystemUtilizationWarnAlert" {
    description = "Alert when the file system utilization exceeds this threshold in percentage. Set to 0 to disable this alert."
    type        = number
    default     = 80
}

variable "fileSystemUtilizationCriticalAlert" {
    description = "Alert when the file system utilization exceeds this threshold in percentage. Set to 0 to disable this alert."
    type        = number
    default     = 90
}

variable "volumeUtilizationWarnAlert" {
    description = "Alert when a volume utilization exceeds this threshold in percentage. Set to 0 to disable this alert."
    type        = number
    default     = 90
}

variable "volumeUtilizationCriticalAlert" {
    description = "Alert when a volume utilization exceeds this threshold in percentage. Set to 0 to disable this alert."
    type        = number
    default     = 95
}

variable "volumeFileUtilizationWarnAlert" {
    description = "Alert when a volume inode utilization exceeds this threshold in percentage. Set to 0 to disable this alert."
    type        = number
    default     = 90
}

variable "volumeFileUtilizationCriticalAlert" {
    description = "Alert when a volume inode utilization exceeds this threshold in percentage. Set to 0 to disable this alert."
    type        = number
    default     = 95
}

variable "volumeOfflineAlert" {
    description = "Alert when a volume goes offline."
    type        = string
    default     = "true"
}

variable "oldSnapshotAlert" {
    description = "Alert when a snapshot is older than the specified number of days. Set to 0 to disable this alert."
    type        = number
    default     = 365
}

variable "softQuotaUtilizationAlert" {
    description = "Alert when a soft quota exceeds this threshold in percentage. Set to 0 to disable this alert."
    type        = number
    default     = 100
}

variable "hardQuotaUtilizationAlert" {
    description = "Alert when a hard quota exceeds this threshold in percentage. Set to 0 to disable this alert."
    type        = number
    default     = 80
}

variable "inodesSoftQuotaUtilizationAlert" {
    description = "Alert when an soft inode quota exceeds this threshold in percentage. Set to 0 to disable this alert."
    type        = number
    default     = 100
}

variable "inodesQuotaUtilizationAlert" {
    description = "Alert when an hard inode quota exceeds this threshold in percentage. Set to 0 to disable this alert."
    type        = number
    default     = 80
}

variable "vserverStateAlert" {
    description = "Alert when a vserver goes offline."
    type        = string
    default     = "true"
}

variable "vserverNFSProtocolStateAlert" {
    description = "Alert when a vserver's NFS protocol goes offline."
    type        = string
    default     = "true"
}

variable "vserverCIFSProtocolStateAlert" {
    description = "Alert when a vserver's CIFS protocol goes offline."
    type        = string
    default     = "true"
}
