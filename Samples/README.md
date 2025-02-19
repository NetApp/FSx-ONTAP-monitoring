# FSx-ONTAP-samples

This subfolder comprehensive code samples and automation scripts for FSx for Netapp ONTAP operations,
promoting the use of Infrastructure as Code (IAC) tools and encouraging developers to extend the product's
functionalities through code. The samples here go alongside the automation, management and monitoring that
[BlueXP Workload Factory](https://console.workloads.netapp.com) provides.

## Table of Contents

* [AI](AI)
    * [GenAI ChatBot application sample](AI/GenAI-ChatBot-application-sample)
* [Automation](Automation)
    * [Ansible](Automation/Ansible)
        * [FSx ONTAP inventory report](Automation/Ansible/FSxN-Inventory-Report)
        * [SnapMirror report](Automation/Ansible/SnapMirror-Report)
    * [CloudFormation](Automation/CloudFormation)
        * [Deploy FSx ONTAP](Automation/CloudFormation/Deploy-FSx-ONTAP)
        * [NetApp FSxN Custom Resources Samples](Automation/CloudFormation/NetApp-FSxN-Custom-Resources-Samples)
    * [Terraform](Automation/Terraform)
        * [Deploy FSx ONTAP](Automation/Terraform/Deploy-FSx-ONTAP)
        * [Deploy FSx ONTAP with VPN for File Share Access](Automation/Terraform/Deploy-FSx-ONTAP-Fileshare-Access)
        * [Deploy of SQL Server on EC2 with FSx ONTAP](Automation/Terraform/Deploy-FSx-ONTAP-SQL-Server)
        * [FSx ONTAP Replication](Automation/Terraform/FSx-ONTAP-Replicate)
* [EKS](EKS)
    * [Collect Non-stdout logs into ELK](EKS/EKS-logs-to-ELK)
* [Management Utilities](Management-Utilities)
    * [Auto Create SnapMirror Relationships](Management-Utilities/Auto-Create-SM-Relationships)
    * [Auto Set Auto Size Mode](Management-Utilities/Auto-Set-Auto-Size-Mode)
    * [AWS CLI Management Scripts for FSx ONTAP](Management-Utilities/FSx-ONTAP-AWS-CLI-Scripts)
    * [Rotate AWS Secrets Manager Secret](Management-Utilities/FSx-ONTAP-Rotate-Secret)
    * [FSx ONTAP iscsi volume creation automation for Windows](Management-Utilities/iSCSI-Vol-Create-and-Mount)
    * [Warm Performance Tier](Management-Utilities/Warm-Performance-Tier)
* [Monitoring](Monitoring)
    * [Automatically Add CloudWatch Alarms for FSx Resources](Monitoring/Auto-Add-CloudWatch-Alarms)
    * [Ingest NAS audit logs into CloudWatch](Monitoring/Ingest-NAS-Audit-Logs-into-CloudWatch)
    * [Monitor FSx ONTAP resources with a Python Lambda Function](Monitoring/Monitor-FSx-ONTAP-Services)

## Author Information

This repository is maintained by the contributors listed on [GitHub](https://github.com/NetApp/FSx-ONTAP-utils/graphs/contributors).

## License

Licensed under the Apache License, Version 2.0 (the "License").

You may obtain a copy of the License at [apache.org/licenses/LICENSE-2.0](http://www.apache.org/licenses/LICENSE-2.0).

Unless required by applicable law or agreed to in writing, software distributed under the License
is distributed on an _"AS IS"_ basis, without WARRANTIES or conditions of any kind, either express or implied.

See the License for the specific language governing permissions and limitations under the License.

© 2025 NetApp, Inc. All Rights Reserved.
