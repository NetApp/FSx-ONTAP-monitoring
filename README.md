# FSx ONTAP Monitoring

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Lint](https://github.com/NetApp/FSx-ONTAP-monitoring/actions/workflows/actionlint.yml/badge.svg)](https://github.com/NetApp/FSx-ONTAP-monitoring/actions/workflows/actionlint.yml)
[![Code Quality: Terraform](https://github.com/NetApp/FSx-ONTAP-monitoring/actions/workflows/terraform.yml/badge.svg)](https://github.com/NetApp/FSx-ONTAP-monitoring/actions/workflows/terraform.yml)
[![GitHub stars](https://img.shields.io/github/stars/NetApp/FSx-ONTAP-monitoring)](https://github.com/NetApp/FSx-ONTAP-monitoring/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/NetApp/FSx-ONTAP-monitoring)](https://github.com/NetApp/FSx-ONTAP-monitoring/network/members)
[![GitHub contributors](https://img.shields.io/github/contributors/NetApp/FSx-ONTAP-monitoring)](https://github.com/NetApp/FSx-ONTAP-monitoring/graphs/contributors)

## Introduction

FSx for NetApp ONTAP is an AWS managed service providing a comprehensive set of advanced storage features purposely
built to minimize cost and maximize performance, resilience, and accessibility in business-critical workloads.

This repository contains utilities for monitoring, alerting and auditing of FSx for ONTAP file systems.

---

## Table of Contents

* [FSx Alerting](FSx_Alerting)
    * [Automatically Add CloudWatch Alarms for FSx Resources](FSx_Alerting/Auto-Add-CloudWatch-Alarms)
    * [Alert on FSx for ONTAP resources](FSx_Alerting/FSx_ONTAP_Alerting)
* [Monitoring FSx with CloudWatch](CloudWatch-Monitoring-FSx)
* [Monitoring FSx with Grafana Prometheus Harvest](Grafana-Prometheus-FSx)
    * [Deploy with EC2](Grafana-Prometheus-FSx/Monitor-FSxN-with-Harvest-on-EC2)
    * [Deploy with EKS](Grafana-Prometheus-FSx/Monitor-FSxN-with-Harvest-on-EKS)
* [FSx Audit Logs](FSx-Audit-Logs)
    * [Ingest FSxN Administrative Audit Logs](FSx-Audit-Logs/Ingest-Administrative-Audit-Logs-CloudWatch)
    * [Ingest FSxN NAS audit logs](FSx-Audit-Logs/Ingest-NAS-Audit-Logs-CloudWatch)

---

If you have any requests for new content, or have any suggestions regarding existing content, please either post you ideas to the
[Ideas](https://github.com/NetApp/FSx-ONTAP-monitoring/discussions/categories/ideas) section in the
[Discussions](https://github.com/NetApp/FSx-ONTAP-monitoring/discussions) tab, or send us an email at
[ng-fsxn-github-samples@netapp.com](mailto:ng-fsxn-github-samples@netapp.com).

We also welcome contributions from the community! Please read our [contribution guidelines](CONTRIBUTING.md) before getting started.

---

## Author Information

This repository is maintained by the contributors listed on [GitHub](https://github.com/NetApp/FSx-ONTAP-monitoring/graphs/contributors).

## License

Licensed under the Apache License, Version 2.0 (the "License").

You may obtain a copy of the License at [apache.org/licenses/LICENSE-2.0](http://www.apache.org/licenses/LICENSE-2.0).

Unless required by applicable law or agreed to in writing, software distributed under the License
is distributed on an _"AS IS"_ basis, without WARRANTIES or conditions of any kind, either express or implied.

See the License for the specific language governing permissions and limitations under the License.

© 2026 NetApp, Inc. All Rights Reserved.
