#
# This is a terraform template to deploy the auto_add_cw_alarms program.
################################################################################

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.region
}

variable "region" {
    description = "The AWS region to deploy the Lambda function and CloudWatch Event rule."
    type        = string
}

variable "SNStopic" {
    description = "The SNS Topic name where CloudWatch will send alerts to. Note that it is assumed that the SNS topic, with the same name, will exist in all the regions where alarms are to be created."
    type        = string
}

variable "accountId" {
    description = "The AWS account ID."
    type        = string
}

variable "customerId" {
    description = "This is really just a comment that will be added to the alarm description."
    type = string
    default = ""
}

variable "defaultCPUThreshold" {
    description = "This will define the default CPU utilization threshold. You can override the default by having a specific tag associated with the file system."
    type = number
    default = 80
    validation {
        condition     = var.defaultCPUThreshold >= 0 && var.defaultCPUThreshold <= 100
        error_message = "The defaultCPUThreshold variable must be between 0 and 100."
    }
}

variable "defaultSSDThreshold" {
    description = "This will define the default SSD (aggregate) utilization threshold. You can override the default by having a specific tag associated with the file system."
    type = number
    default = 80
    validation {
        condition     = var.defaultSSDThreshold >= 0 && var.defaultSSDThreshold <= 100
        error_message = "The defaultSSDThreshold variable must be between 0 and 100."
    }
}

variable "defaultVolumeThreshold" {
    description = "This will define the default Volume utilization threshold. You can override the default by having a specific tag associated with the volume."
    type = number
    default = 80
    validation {
        condition     = var.defaultVolumeThreshold >= 0 && var.defaultVolumeThreshold <= 100
        error_message = "The defaultVolumeThreshold variable must be between 0 and 100."
    }
}

variable "defaultVolumeFilesThreshold" {
    description = "This will define the default Volume files (inodes) utilization threshold. You can override the default by having a specific tag associated with the volume."
    type = number
    default = 80
    validation {
        condition     = var.defaultVolumeFilesThreshold >= 0 && var.defaultVolumeFilesThreshold <= 100
        error_message = "The defaultVolumeFilesThreshold variable must be between 0 and 100."
    }
}

variable "checkInterval" {
    description = "This is how often you want the Lambda function to run to look for new file systems and/or volumes (minutes)."
    type = number
    default = 15
    validation {
        condition     = var.checkInterval >= 0
        error_message = "The checkInterval variable must be greater than 0."
    }
}

variable "alarmPrefixString" {
    description = "This is the string that will be prepended to all CloudWatch alarms created by this script."
    type = string
    default = "FSx-ONTAP-Auto"
}

variable "regions" {
    description = "This is a list of AWS regions that you want the Lambda function to run in. If left blank, it will run in all regions."
    type = string
    default = ""
}

resource "random_integer" "unique_id" {
  min = 1
  max = 999999
}

resource "aws_iam_role" "auto_add_cw_alarms_lambda_role" {
  name = "auto_add_cw_alarms-${random_integer.unique_id.result}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}
resource "aws_iam_role_policy" "auto_add_cw_alarms_lambda_policy" {
  name = "auto_add_cw_alarms_lambda_policy-${random_integer.unique_id.result}"
  role = aws_iam_role.auto_add_cw_alarms_lambda_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "fsx:DescribeFileSystems",
          "fsx:DescribeVolumes",
          "fsx:ListTagsForResource",
          "ec2:DescribeRegions",
          "cloudwatch:DescribeAlarms",
          "cloudwatch:DescribeAlarmsForMetric",
          "cloudwatch:PutMetricAlarm"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:DeleteAlarms"
        ]
        Resource = "arn:aws:cloudwatch:*:${var.accountId}:alarm:${var.alarmPrefixString}*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic_execution_role_controller" {
  role       = aws_iam_role.auto_add_cw_alarms_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_cloudwatch_event_rule" "lambda_event_rule" {
  description = "Event rule to trigger the auto-add-cw-alarms Lambda function on a schedule."
  name        = "auto-add-cw-alarms-rule-${random_integer.unique_id.result}"
  schedule_expression = "rate(${var.checkInterval} minutes)"
  state       = "ENABLED"
}
resource "aws_cloudwatch_event_target" "lambda_event_target" {
  rule      = aws_cloudwatch_event_rule.lambda_event_rule.name
  arn       = aws_lambda_function.auto_add_cw_alarms_lambda_function.arn
  target_id = "auto_add_cw_alarms_lambda_target"
}
#
# This allows the EventBridge rule to invoke the controller Lambda function.
resource "aws_lambda_permission" "lambda_permission_event_rule" {
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.auto_add_cw_alarms_lambda_function.arn
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.lambda_event_rule.arn
}

data "archive_file" "auto_add_cw_alarms_source" {
  type        = "zip"
  output_path = "auto_add_cw_alarms.zip"
  source_file = "../auto_add_cw_alarms.py"
}

resource "aws_lambda_function" "auto_add_cw_alarms_lambda_function" {
  function_name = "Lambda_for_auto_add_cw_alarms-${random_integer.unique_id.result}"
  role = aws_iam_role.auto_add_cw_alarms_lambda_role.arn
  package_type     = "Zip"
  runtime          = "python3.12"
  handler          = "auto_add_cw_alarms.lambda_handler"
  filename         = "auto_add_cw_alarms.zip"
  depends_on       = [data.archive_file.auto_add_cw_alarms_source]
  timeout          = 300

  environment {
    variables = {
      SNStopic = var.SNStopic
      accountId = var.accountId
      customerId = var.customerId
      defaultCPUThreshold = var.defaultCPUThreshold
      defaultSSDThreshold = var.defaultSSDThreshold
      defaultVolumeThreshold = var.defaultVolumeThreshold
      defaultVolumeFilesThreshold = var.defaultVolumeFilesThreshold
      basePrefix = var.alarmPrefixString
      regions = var.regions
    }
  }
}
