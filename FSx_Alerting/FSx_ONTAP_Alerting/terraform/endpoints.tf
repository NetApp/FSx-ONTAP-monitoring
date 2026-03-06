################################################################################
# This file creates the VPC endpoints for the services that are required by
# Monitor ONTAP Services program.
################################################################################

resource "aws_vpc_endpoint" "secrets_manager_endpoint" {
  count               = var.createSecretsManagerEndpoint ? 1 : 0
  vpc_id              = var.vpcId
  service_name        = "com.amazonaws.${var.region}.secretsmanager"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = var.subNetIds
  security_group_ids  = var.endpointSecurityGroupIds
}

resource "aws_vpc_endpoint" "cloudwatch_logs_endpoint" {
  count               = var.createCloudWatchLogsEndpoint ? 1 : 0
  vpc_id              = var.vpcId
  service_name        = "com.amazonaws.${var.region}.logs"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = var.subNetIds
  security_group_ids  = var.endpointSecurityGroupIds
}

resource "aws_vpc_endpoint" "sns_endpoint" {
  count               = var.createSNSEndpoint ? 1 : 0
  vpc_id              = var.vpcId
  service_name        = "com.amazonaws.${var.region}.sns"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = var.subNetIds
  security_group_ids  = var.endpointSecurityGroupIds
}

resource "aws_vpc_endpoint" "s3_endpoint" {
  count             = var.createS3Endpoint ? 1 : 0
  vpc_id            = var.vpcId
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = var.routeTableIds
}
