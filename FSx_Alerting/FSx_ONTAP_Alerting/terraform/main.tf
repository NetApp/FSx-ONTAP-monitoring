################################################################################
# The terraform code in this directory will create the necessary resources
# to deploy the Monitor Ontap Services solution.
################################################################################

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

# Configure the AWS Provider
provider "aws" {
  region = var.region
}

resource "random_integer" "unique_id" {
  min = 1
  max = 999999
}
#
# This is the role and policies that will be assigned to the controller Lambda
# function if the user doesn't provide a role ARN.
resource "aws_iam_role" "controller_role" {
  count = var.controllerRoleArn == "" ? 1 : 0
  name = "controller-MOS-${random_integer.unique_id.result}"
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
resource "aws_iam_role_policy" "controller_policy" {
  count = var.controllerRoleArn == "" ? 1 : 0
  name = "controllerPolicy"
  role = aws_iam_role.controller_role[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction",
          "s3:GetObject",
          "sns:Publish",
        ]
        Resource = [
          var.snsTopicArn,
          aws_lambda_function.monitor_ontap_services_lambda_function.arn,
          "arn:aws:s3:::${var.s3BucketName}/*"
        ]
      }
    ]
  })
}
resource "aws_iam_role_policy_attachment" "lambda_basic_execution_role_controller" {
  count = var.controllerRoleArn == "" ? 1 : 0
  role       = aws_iam_role.controller_role[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}
#
# Instead of creating a EventBridge schedule, create an EventBridge rule
# triggered by a schedule. This way a separate role doesn't have to be
# created, just a Lambda permission to allow EventBridge to invoke the
# Lambda function.
resource "aws_cloudwatch_event_rule" "lambda_event_rule" {
  description = "Event rule to trigger the MOS-controller Lambda function."
  name        = "MOS-controller-rule-${random_integer.unique_id.result}"
  schedule_expression = "rate(${var.checkInterval} minutes)"
  state       = "ENABLED"
}
resource "aws_cloudwatch_event_target" "lambda_event_target" {
  rule      = aws_cloudwatch_event_rule.lambda_event_rule.name
  arn       = aws_lambda_function.controller_lambda_function.arn
  target_id = "MonitorOntapServicesTarget"
}
#
# This allows the EventBridge rule to invoke the controller Lambda function.
resource "aws_lambda_permission" "lambda_permission_event_rule" {
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.controller_lambda_function.arn
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.lambda_event_rule.arn
}
#
# This will create a zip file of the controller Lambda function code.
data "archive_file" "controller_source" {
  type        = "zip"
  output_path = "controller.zip"
  source_file = "../controller.py"
}

resource "aws_lambda_function" "controller_lambda_function" {
  function_name = "MOS-controller-${random_integer.unique_id.result}"
  role = var.controllerRoleArn != "" ? var.controllerRoleArn : aws_iam_role.controller_role[0].arn
  package_type     = "Zip"
  runtime          = "python3.12"
  handler          = "controller.lambda_handler"
  filename         = "controller.zip"
  depends_on       = [data.archive_file.controller_source]
  timeout          = 60

  environment {
    variables = {
      s3BucketRegion        = var.region
      s3BucketName          = var.s3BucketName
      FSxNList              = var.FSxNListFilename
      snsTopicArn           = var.snsTopicArn
      MOSLambdaFunctionName = aws_lambda_function.monitor_ontap_services_lambda_function.function_name

      initialVersionChangeAlert = var.versionChangeAlert
      initialFailoverAlert = var.failoverAlert
      initialEmsEventsAlert = var.emsEventsAlert
      initialSnapMirrorLagTimeAlert = var.snapMirrorLagTimeAlert
      initialSnapMirrorLagTimePercentAlert = var.snapMirrorLagTimePercentAlert
      initialSnapMirrorStalledAlert = var.snapMirrorStalledAlert
      initialSnapMirrorHealthAlert = var.snapMirrorHealthAlert
      initialFileSystemUtilizationWarnAlert = var.fileSystemUtilizationWarnAlert
      initialFileSystemUtilizationCriticalAlert = var.fileSystemUtilizationCriticalAlert
      initialVolumeUtilizationWarnAlert = var.volumeUtilizationWarnAlert
      initialVolumeUtilizationCriticalAlert = var.volumeUtilizationCriticalAlert
      initialVolumeFileUtilizationWarnAlert = var.volumeFileUtilizationWarnAlert
      initialVolumeFileUtilizationCriticalAlert = var.volumeFileUtilizationCriticalAlert
      initialVolumeOfflineAlert = var.volumeOfflineAlert
      initialOldSnapshot = var.oldSnapshotAlert
      initialSoftQuotaUtilizationAlert = var.softQuotaUtilizationAlert
      initialHardQuotaUtilizationAlert = var.hardQuotaUtilizationAlert
      initialInodesQuotaUtilizationAlert = var.inodesQuotaUtilizationAlert
      initialInodesSoftQuotaUtilizationAlert = var.inodesSoftQuotaUtilizationAlert
      initialVserverStateAlert = var.vserverStateAlert
      initialVserverNFSProtocolStateAlert = var.vserverNFSProtocolStateAlert
      initialVserverCIFSProtocolStateAlert = var.vserverCIFSProtocolStateAlert
    }
  }
}
#
# This is the role and policies that will be assigned to the monitoring Lambda
# function if the user doesn't provide a role ARN.
resource "aws_iam_role" "monitoring_lambda_role" {
  count = var.monitorRoleArn == "" ? 1 : 0
  name = "monitor-ontap-services-${random_integer.unique_id.result}"
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

resource "aws_iam_role_policy" "monitoring_lambda_policy" {
  count = var.monitorRoleArn == "" ? 1 : 0
  name = "LambdaPolicy"
  role = aws_iam_role.monitoring_lambda_role[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "sns:Publish",
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ]
        Resource = [
          var.secretArnPattern,
          var.snsTopicArn,
          "arn:aws:s3:::${var.s3BucketName}",
          "arn:aws:s3:::${var.s3BucketName}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:DescribeLogStreams"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "monitoring_lambda_role_vpc_execution_role" {
  count      = var.monitorRoleArn == "" ? 1 : 0
  role       = aws_iam_role.monitoring_lambda_role[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_lambda_layer_version" "lambda_layer" {
  count               = var.lambdaLayerArn == "" ? 1 : 0
  layer_name          = "MOS-${random_integer.unique_id.result}"
  compatible_runtimes = ["python3.12"]
  s3_key              = "lambda_layer.zip"
  s3_bucket           = var.s3BucketName
}

data "archive_file" "monitor_ontap_services_source" {
  type        = "zip"
  output_path = "monitor_ontap_services.zip"
  source_file = "../monitor_ontap_services.py"
}

resource "aws_lambda_function" "monitor_ontap_services_lambda_function" {
  function_name = "monitor-ontap-services-${random_integer.unique_id.result}"
  role = var.monitorRoleArn != "" ? var.monitorRoleArn : aws_iam_role.monitoring_lambda_role[0].arn
  vpc_config {
    security_group_ids = var.securityGroupIds
    subnet_ids         = var.subNetIds
  }
  package_type     = "Zip"
  runtime          = "python3.12"
  layers           = var.lambdaLayerArn != "" ? [var.lambdaLayerArn] : [aws_lambda_layer_version.lambda_layer[0].arn]
  handler          = "monitor_ontap_services.lambda_handler"
  timeout          = var.maxRunTime
  memory_size      = var.memorySize
  filename         = "monitor_ontap_services.zip"
  depends_on       = [data.archive_file.monitor_ontap_services_source]
}
