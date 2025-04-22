# FSx-ONTAP-utils

FSx for NetApp ONTAP is an AWS managed service providing a comprehensive set of advanced storage features purposely
built to maximize cost, performance, resilience, and accessibility in business-critical workloads.

## Overview

This GitHub repository contains both NetApp maintained and community-contributed samples and scripts for FSx for NetApp ONTAP.
The community-contributed samples are found in the Samples folder. All other folders contain NetApp developed and maintained utilities.

All of the content in this repository is here to enhance the user experience with FSx for NetApp ONTAP by providing
automation scripts, management utilities and monitoring solutions. These utilities complement the NetApp provided
management tool [BlueXP Workload Factory](https://console.workloads.netapp.com).

If you have any requests for new content, or have any suggestions regarding existing content, please either post you ideas to the
[Ideas](https://github.com/NetApp/FSx-ONTAP-utils/discussions/categories/ideas) section in the
[Discussions](https://github.com/NetApp/FSx-ONTAP-utils/discussions) tab, or send us an email at
[ng-fsxn-github-samples@netapp.com](mailto:ng-fsxn-github-samples@netapp.com).

We also welcome contributions from the community! Please read our [contribution guidelines](CONTRIBUTING.md) before getting started.

## Table of Contents

* FSxN Utilities by NetApp
    * [Monitoring](/Monitoring)
        * [CloudWatch Dashboard for FSx for ONTAP](/Monitoring/CloudWatch-FSx)
        * [Ingest NAS audit logs into CloudWatch](/Monitoring/Ingest-NAS-Audit-Logs-into-CloudWatch)
        * [Grafana Dashboard for FSx for ONTAP](/Monitoring/Grafana)
    * [EKS](/EKS)
        * [Backup EKS Applications with Trident Protect](/EKS/Backup-EKS-Applications-with-Trident-Protect)
        * [FSx for NetApp ONTAP as persistent storage for EKS](/EKS/FSxN-as-PVC-for-EKS)
        * [PV Migrate with Trident Protect](/EKS/PV-Migrate-with-Trident-Protect)
* Community Maintained Samples
    * [AI](/Samples/AI)
        * [GenAI ChatBot application sample](/Samples/AI/GenAI-ChatBot-application-sample)
    * [Automation](/Samples/Automation)
        * [Ansible](/Samples/Automation/Ansible)
            * [FSx ONTAP inventory report](/Samples/Automation/Ansible/FSxN-Inventory-Report)
            * [SnapMirror report](/Samples/Automation/Ansible/SnapMirror-Report)
        * [CloudFormation](/Samples/Automation/CloudFormation)
            * [Deploy FSx ONTAP](/Samples/Automation/CloudFormation/Deploy-FSx-ONTAP)
            * [NetApp FSxN Custom Resources Samples](/Samples/Automation/CloudFormation/NetApp-FSxN-Custom-Resources-Samples)
        * [Terraform](/Samples/Automation/Terraform)
            * [Deploy FSx ONTAP](/Samples/Automation/Terraform/Deploy-FSx-ONTAP)
            * [Deploy FSx ONTAP with VPN for File Share Access](/Samples/Automation/Terraform/Deploy-FSx-ONTAP-Fileshare-Access)
            * [Deploy of SQL Server on EC2 with FSx ONTAP](/Samples/Automation/Terraform/Deploy-FSx-ONTAP-SQL-Server)
            * [FSx ONTAP Replication](/Samples/Automation/Terraform/FSx-ONTAP-Replicate)
    * [EKS](/Samples/EKS)
        * [Collect Non-stdout logs into ELK](/Samples/EKS/EKS-logs-to-ELK)
    * [Management Utilities](/Samples/Management-Utilities)
        * [Auto Create SnapMirror Relationships](/Samples/Management-Utilities/Auto-Create-SM-Relationships)
        * [Auto Set Auto Size Mode](/Samples/Management-Utilities/Auto-Set-Auto-Size-Mode)
        * [AWS CLI Management Scripts for FSx ONTAP](/Samples/Management-Utilities/FSx-ONTAP-AWS-CLI-Scripts)
        * [Rotate AWS Secrets Manager Secret](/Samples/Management-Utilities/FSx-ONTAP-Rotate-Secret)
        * [FSx ONTAP iSCSI volume creation automation for Windows](/Samples/Management-Utilities/iSCSI-Vol-Create-and-Mount)
        * [Warm Performance Tier](/Samples/Management-Utilities/Warm-Performance-Tier)
    * [Monitoring](/Samples/Monitoring)
        * [Automatically Add CloudWatch Alarms for FSx Resources](/Samples/Monitoring/Auto-Add-CloudWatch-Alarms)
        * [Monitor FSx ONTAP resources with a Python Lambda Function](/Samples/Monitoring/Monitor-FSx-ONTAP-Services)

## Author Information

This repository is maintained by the contributors listed on [GitHub](https://github.com/NetApp/FSx-ONTAP-utils/graphs/contributors).

## License

Licensed under the Apache License, Version 2.0 (the "License").

You may obtain a copy of the License at [apache.org/licenses/LICENSE-2.0](http://www.apache.org/licenses/LICENSE-2.0).

Unless required by applicable law or agreed to in writing, software distributed under the License
is distributed on an _"AS IS"_ basis, without WARRANTIES or conditions of any kind, either express or implied.

See the License for the specific language governing permissions and limitations under the License.

© 2025 NetApp, Inc. All Rights Reserved.
