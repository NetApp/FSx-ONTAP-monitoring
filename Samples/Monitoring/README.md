# Monitoring Overview
This subfolder contains tools that can help you monitor your FSx ONTAP file system.

| Tool | Description |
| --- | --- |
| [Auto Add CloudWatch Alarms](Auto-Add-CloudWatch-Alarms) | This tool will automatically add CloudWatch alarms that will alert you when:<br><ul><li>The utilization of the primary storage of any FSx ONTAP file system gets above a specified threshold.</li><li>The CPU utilization of any file system gets above a specified threshold.</li><li>The utilization of any volume within any file system gets above a specified threshold.</li></ul>|
| [Ingest NAS Audit Logs to CloudWatch](Ingest-NAS-Audit-Logs-into-CloudWatch) | This tool will help you ingest NAS audit logs from FSx ONTAP into CloudWatch.|
| [Monitor FSx ONTAP Services](Monitor-FSx-ONTAP-Services)| This tool helps you monitor various Data ONTAP services and send SNS alerts if anything of interest is detected. The following services are monitored:<br><ul><li>EMS Messages</li><li>SnapMirror health, including tag time</li><li>Aggregate, volume or Quota utilization based on user provided thresholds</li><li>Overall health of the File System</ul>|

## Author Information

This repository is maintained by the contributors listed on [GitHub](https://github.com/NetApp/FSx-ONTAP-utils/graphs/contributors).

## License

Licensed under the Apache License, Version 2.0 (the "License").

You may obtain a copy of the License at [apache.org/licenses/LICENSE-2.0](http://www.apache.org/licenses/LICENSE-2.0).

Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an _"AS IS"_ basis, without WARRANTIES or conditions of any kind, either express or implied.

See the License for the specific language governing permissions and limitations under the License.

© 2024 NetApp, Inc. All Rights Reserved.
