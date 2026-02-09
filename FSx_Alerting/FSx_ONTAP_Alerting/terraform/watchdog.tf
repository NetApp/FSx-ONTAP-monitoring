################################################################################
# This file create the watchdog CloudWatch alarms and optionally a proxy
# Lambda function that will send an SNS alert to a topic in another region
# since CloudWatch itself can't do that. The watchdog alarm will alert if
# the monitoring or controller Lambda functions return an error status.
################################################################################

################################################################################
# These two CloudWatch alarms will monitor the monitoring and controller
# Lambda functions and send an alert directly to the SNS topic if the function
# fails to run properly. Either these alarms, or the ones that triggers the
# watchdog Lambda function will be created if the user selects
# to create the watchdog alarms.
################################################################################
resource "aws_cloudwatch_metric_alarm" "watchdog_alarm_to_sns" {
  count = var.createWatchdogAlarm && !var.implementWatchdogAsLambda ? 1 : 0
  alarm_name         = "MOS-watchdog-${random_integer.unique_id.result}"
  alarm_description  = "Watchdog alarm for the monitor-ontap-services-${random_integer.unique_id.result} Lambda function."
  namespace          = "AWS/Lambda"
  metric_name        = "Errors"
  dimensions = {
    FunctionName = "monitor-ontap-services-${random_integer.unique_id.result}"
  }
  statistic          = "Maximum"
  period             = 300
  evaluation_periods = 1
  treat_missing_data = "ignore"
  threshold          = 0.5
  comparison_operator = "GreaterThanThreshold"
  alarm_actions      = [var.snsTopicArn]
}

resource "aws_cloudwatch_metric_alarm" "watchdog_controller_alarm_to_sns" {
  count = var.createWatchdogAlarm && !var.implementWatchdogAsLambda ? 1 : 0
  alarm_name         = "MOS-controller-watchdog-${random_integer.unique_id.result}"
  alarm_description  = "Watchdog alarm for the MOS-controller-${random_integer.unique_id.result} Lambda function."
  namespace          = "AWS/Lambda"
  metric_name        = "Errors"
  dimensions = {
    FunctionName = "MOS-controller-${random_integer.unique_id.result}"
  }
  statistic          = "Maximum"
  period             = 300
  evaluation_periods = 1
  treat_missing_data = "ignore"
  threshold          = 0.5
  comparison_operator = "GreaterThanThreshold"
  alarm_actions      = [var.snsTopicArn]
}

################################################################################
# The rest of this file is related to creating a watchdog solution that is able
# to send SNS alerts to another region.
################################################################################
resource "aws_iam_role" "lambda_role_watchdog" {
  count =  var.createWatchdogAlarm && var.implementWatchdogAsLambda && var.watchdogRoleArn == "" ? 1 : 0
  name = "MOS-watchdog-proxy-${random_integer.unique_id.result}"
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
resource "aws_iam_role_policy" "lambda_policy_watchdog" {
  count =  var.createWatchdogAlarm && var.implementWatchdogAsLambda && var.watchdogRoleArn == "" ? 1 : 0
  name = "LambdaPolicyWatchdog"
  role = aws_iam_role.lambda_role_watchdog[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = var.snsTopicArn
      }
    ]
  })
}
resource "aws_iam_role_policy_attachment" "lambda_basic_execution_role_watchdog" {
  count      = var.implementWatchdogAsLambda && var.watchdogRoleArn == "" ? 1 : 0
  role       = aws_iam_role.lambda_role_watchdog[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}
#
# This is the source code to the Lambda function that will publish to the SNS topic
# in aother region.
data "archive_file" "watchdog_lambda_function_source" {
  count = var.implementWatchdogAsLambda ? 1 : 0
  type        = "zip"
  output_path = "watchdog_lambda_function.zip"
  source {
    content = <<-EOF
      import boto3
      import os
      
      def lambda_handler(event, context):
          snsTopicArn = os.environ.get('snsTopicArn')
          if snsTopicArn is not None:
              snsClient = boto3.client('sns', region_name=snsTopicArn.split(":")[3])
              snsClient.publish(
                  TopicArn = snsTopicArn,
                  Subject  = 'Error! Monitoring ONTAP services has failed to execute',
                  Message  = f'Error! Lambda function {event["alarmData"]["alarmName"].replace("-watchdog-", "")} failed to execute properly.'
              )
    EOF
    filename = "index.py"
  }
}
resource "aws_lambda_function" "watchdog_lambda_function" {
  count = var.createWatchdogAlarm && var.implementWatchdogAsLambda ? 1 : 0
  function_name = "MOS-watchdog-proxy-${random_integer.unique_id.result}"
  package_type = "Zip"
  runtime = "python3.12"
  handler = "index.lambda_handler"
  timeout = 10
  role = var.watchdogRoleArn == "" ? aws_iam_role.lambda_role_watchdog[0].arn : var.watchdogRoleArn
  environment {
    variables = {
      snsTopicArn = var.snsTopicArn
    }
  }
  filename         = "watchdog_lambda_function.zip"
  depends_on       = [data.archive_file.watchdog_lambda_function_source]
}
#
# These two resources allow the monitoring and controller CloudWatch "watchdog" alarms to invoke the proxy Lambda function.
resource "aws_lambda_permission" "resource_based_permission-monitoring" {
  count = var.createWatchdogAlarm && var.implementWatchdogAsLambda ? 1 : 0
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.watchdog_lambda_function[0].function_name
  principal     = "lambda.alarms.cloudwatch.amazonaws.com"
  source_arn    = aws_cloudwatch_metric_alarm.watchdog_alarm_to_lambda[0].arn
}
resource "aws_lambda_permission" "resource_based_permission" {
  count = var.createWatchdogAlarm && var.implementWatchdogAsLambda ? 1 : 0
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.watchdog_lambda_function[0].function_name
  principal     = "lambda.alarms.cloudwatch.amazonaws.com"
  source_arn    = aws_cloudwatch_metric_alarm.watchdog_controller_alarm_to_lambda[0].arn
}

resource "aws_cloudwatch_metric_alarm" "watchdog_alarm_to_lambda" {
  count = var.createWatchdogAlarm && var.implementWatchdogAsLambda ? 1 : 0
  alarm_name         = "MOS-watchdog-${random_integer.unique_id.result}"
  alarm_description  = "Watchdog alarm for the monitor-ontap-services-${random_integer.unique_id.result} Lambda function."
  namespace          = "AWS/Lambda"
  metric_name        = "Errors"
  dimensions = {
    FunctionName = "monitor-ontap-services-${random_integer.unique_id.result}"
  }
  statistic          = "Maximum"
  period             = 300
  evaluation_periods = 1
  treat_missing_data = "ignore"
  threshold          = 0.5
  comparison_operator = "GreaterThanThreshold"
  alarm_actions      = [aws_lambda_function.watchdog_lambda_function[0].arn]
}

resource "aws_cloudwatch_metric_alarm" "watchdog_controller_alarm_to_lambda" {
  count = var.createWatchdogAlarm && var.implementWatchdogAsLambda ? 1 : 0
  alarm_name         = "MOS-watchdog-${random_integer.unique_id.result}"
  alarm_description  = "Watchdog alarm for the MOS-controller-${random_integer.unique_id.result} Lambda function."
  namespace          = "AWS/Lambda"
  metric_name        = "Errors"
  dimensions = {
    FunctionName = "MOS-controller-${random_integer.unique_id.result}"
  }
  statistic          = "Maximum"
  period             = 300
  evaluation_periods = 1
  treat_missing_data = "ignore"
  threshold          = 0.5
  comparison_operator = "GreaterThanThreshold"
  alarm_actions      = [aws_lambda_function.watchdog_lambda_function[0].arn]
}
