# Deploy NetApp Harvest on EC2

A NetApp Harvest installation for monitoring Amazon FSx for ONTAP File Systems using a NetApp Harvest, Prometheus and Grafana stack, integrated AWS Secret Manager for FSx for ONTAP credentials.

## Introduction

### What to Expect

By following this guide, you will:
* Create a AWS Secret Manager secret for each FSxN you want to monitor.
* Create an IAM policy that has the required permissions to access the AWS Secret Manager secrets and CloudWatch metrics.
* Optionally create an IAM instance profile with the policy attached to it.
* Optionally create an EC2 instance.
* Deploy Docker on the EC2 instance and have it run containerized version of Prometheus, Grafana, NetApp Harvest and YACE (Yet Another CloudWatch Exporter).
* Collecting metrics from your FSxNs and adding Grafana dashboards for better visualization.

### Prerequisites
* A FSx for ONTAP file system running in the same VPC as the EC2 instance.
* Optionally, an EC2 instance to run the monitoring stack on. If you don't already have one, the steps below will guide you through creating one with the necessary permissions.

## Installation Steps

### 1. Create AWS Secret Manager with Username and Password for each FSxN
Since this solution uses an AWS Secrets Manager secret to authenticate with the FSx for ONTAP file system
you will need to create a secret for each FSxN you want to monitor. You can use the same secret for multiple
file systems if the credentials are the same. The secret should have two key/value pairs:
- `username`: The username to authenticate with the FSxN.
- `password`: The password to authenticate with the FSxN.

Here is how you can create one using the `aws` command:

```sh
aws secretsmanager create-secret --name <YOUR-SECRET-NAME> --secret-string '{"username":"fsxadmin","password":"<YOUR-PASSWORD>"}' --tags Key=fsxmonitoring,Value=true
```

**NOTE:** The 'fsxmonitoring' tag is used in the IAM policy so you don't have to specify each secret ARN in the policy. If you don't want to use the tag, you can specify the secret ARN in the policy instead.

### 2. Create Instance Profile with Permission to access the AWS Secret Manager and CloudWatch metrics

#### 2.1. Create Policy

Run the following commands to create a policy that gives the required permissions to allow Harvest to access
the AWS Secrets Manager secrets and YACE to retrieve CloudWatch metrics.
It assumes that the 'fsxmonitoring' tag is applied to any secrets you created in step 1.
It will set the `POLICY_ARN` variable to the ARN of the created policy, which you will need in the next step.
```sh
cat <<EOF > harvest-policy.json
{
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": [
        "*"
      ],
      "Condition":{
          "StringEquals": {
             "aws:ResourceTag/fsxmonitoring": "true"
          }
      }
    },
    {
      "Effect": "Allow",
      "Action": [
        "tag:GetResources",
        "cloudwatch:GetMetricData",
        "cloudwatch:GetMetricStatistics",
        "cloudwatch:ListMetrics"
      ],
      "Resource": [
        "*"
      ]
    }
  ],
  "Version": "2012-10-17"
}
EOF
POLICY_ARN=$(aws iam create-policy --policy-name harvest-policy --policy-document file://harvest-policy.json --query Policy.Arn --output text)
echo "The policy ARN is: $POLICY_ARN"
```

#### 2.2. Create Instance Profile Role

If you already have an EC2 instance and it already has a Instance Profile Role attached to it,
then you need to assign the policy created in the step above to that role.
Otherwise, run the following commands to create the instance profile role and attach the policy to it:
```sh
cat <<EOF > trust-policy.json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ec2.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
aws iam create-role --role-name HarvestRole --assume-role-policy-document file://trust-policy.json
aws iam attach-role-policy --role-name HarvestRole --policy-arn $POLICY_ARN
INSTANCE_PROFILE_ARN=$(aws iam create-instance-profile --instance-profile-name HarvestProfile --query InstanceProfile.Arn --output text)
echo "The instance profile ARN is: $INSTANCE_PROFILE_ARN"
aws iam add-role-to-instance-profile --instance-profile-name HarvestProfile --role-name HarvestRole
```

### 3. Create EC2 Instance and assign the instance profile
If you don't already have an EC2 instance to run the monitoring solution in you can use the AWS console, or the `aws` command,
to create one. Since there are so many different options to create an EC2 instance it is beyond the scope
of this guide to cover all of them. However, here are some recommendations:

- It should be in the same VPC as your FSxN file systems.
- It must have connectivity to the FSxN management endpoints.
- It must have connectivity to the Internet so it can download the Docker images and updates.
- You should allocate at least 2 vCPUs and 1GB of RAM for every 10 FSxN file systems you plan to monitor
    - Use at least a `t3.medium`.
- Allocate at least 20GB disk.

Once you have created your EC2 instance, or if you already had one, obtain its instance ID and run the following command to attach the instance profile:

```sh
aws ec2 associate-iam-instance-profile --instance-id <INSTANCE-ID> --iam-instance-profile Arn=$INSTANCE_PROFILE_ARN,Name=HarvestProfile
```
**NOTES:**
- Replace <INSTANCE_ID> with the instance ID of your EC2 instance
- The above command assume you created the instance profile using the example above. If you didn't use that, then replace $INSTANCE_PROFILE_ARN with the ARN of your instance profile.

### 4. Install Docker, Docker Compose, and some other needed utilities

**Note:** Almost all the commands below require root permissions to run, so you will need to use `sudo` for each command or execute `sudo -i` to switch to a root shell.

#### 4.1 Log into your EC2 instance
If you haven't already, log into your EC2 instance using SSH and assume 'root' privileges. The command will look something like this:
```sh
ssh -i /path/to/your/key.pem ec2-user@<IP_OF_EC2_INSTANCE>
sudo -i
```

#### 4.2 Install Docker and needed utilities
Use the following commands to install Docker if you are running an Amazon Linux 2023:
```sh
dnf update -y
dnf install -y jq curl wget unzip dnf-plugins-core
dnf install -y docker
```
If you aren't running a Amazon Linux 2023 you can follow the [Docker installation instructions](https://docs.docker.com/engine/install/) from the Docker website for your instructions on your specific Linux distribution.

#### 4.2 Install Docker Compose:
Use the following commands to install the latest version of Docker compose:
```text
LATEST_COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | jq -r '.tag_name')
ARCH=$(uname -m)
if [ -z "$ARCH"  -o -z "$LATEST_COMPOSE_VERSION" ]; then
  echo "Error: Unable to determine latest version or architecture."
else
  curl -s -L "https://github.com/docker/compose/releases/download/$LATEST_COMPOSE_VERSION/docker-compose-linux-$ARCH" -o /usr/local/bin/docker-compose
  chmod +x /usr/local/bin/docker-compose
  # Create a symlink in /usr/bin for more accessibility.
  [ ! -L /usr/bin/docker-compose ] && ln -s /usr/local/bin/docker-compose /usr/bin/docker-compose
fi
```

If you are running SELinux, you need to set the SELinux context for Docker to work properly. You can do this by running:

```sh
cat <<EOF > /etc/docker/daemon.json
{
  "exec-opts": ["native.cgroupdriver=systemd"],
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "storage-driver": "overlay2"
}
EOF
```
Now, bring up the Docker service and enabling it to start on boot:

```sh
systemctl enable docker
systemctl start docker
```

To confirm that Docker has been installed correctly, run the following command:

```sh
docker run hello-world
```

You should get output similar to the following:
```
Hello from Docker!
This message shows that your installation appears to be working correctly.

To generate this message, Docker took the following steps:
 1. The Docker client contacted the Docker daemon.
 2. The Docker daemon pulled the "hello-world" image from the Docker Hub.
    (amd64)
 3. The Docker daemon created a new container from that image which runs the
    executable that produces the output you are currently reading.
 4. The Docker daemon streamed that output to the Docker client, which sent it
    to your terminal.

To try something more ambitious, you can run an Ubuntu container with:
 $ docker run -it ubuntu bash

Share images, automate workflows, and more with a free Docker ID:
 https://hub.docker.com/

For more examples and ideas, visit:
 https://docs.docker.com/get-started/
```

### 5. Install Harvest

Preform the following steps to install Harvest on your EC2 instance.

#### 5.1. Create a directory to work in

A lot of the example commands below assume you are running from the /opt/harvest directory.
```sh
mkdir -p /opt/harvest
cd /opt/harvest
```

If you are running within a SELinux enabled environment, you will need to set the SELinux context for the `/opt/harvest` directory.
```sh
semanage fcontext -a -t container_file_t "/opt/harvest(/.*)?"
restorecon -R /opt/harvest
```

#### 5.2. Generate Harvest Configuration File

Create harvest configuration file `harvest.yml` by running the following command:

```text
cat <<EOF > harvest.yml
Exporters:
    prometheus1:
        exporter: Prometheus
        port_range: 12990-14000
        add_meta_tags: false
Defaults:
    use_insecure_tls: true
Pollers:
    dummyfsx00:
        datacenter: fsx
EOF
```
Don't worry about the `dummyfsx00` poller, it will be replaced later by the `update_clusters.sh` script.

#### 5.3. Generate a Docker Compose from Harvest Configuration

Run the following command to generate a Docker Compose files from the Harvest configuration:

```sh
docker run --rm \
  --env UID=$(id -u) --env GID=$(id -g) \
  --entrypoint "bin/harvest" \
  --volume "$(pwd):/opt/temp" \
  --volume "$(pwd)/harvest.yml:/opt/harvest/harvest.yml" \
  ghcr.io/netapp/harvest \
  generate docker full \
  --output harvest-compose.yml
```

:warning: Ignore the command that it outputs that it says will start the cluster.

#### 5.4. Replace images for Prometheus and Grafana to be the latest images in the prom-stack.yml:

The above command generates a `prom-stack.yml` file that calls for an old versions of Prometheus and Grafana.
Run the following command to have it always run the latest version:

```yaml
sed -i -e 's,image: grafana/grafana:.*,image: grafana/grafana:latest,' -e 's,image: prom/prometheus:.*,image: prom/prometheus:latest,' prom-stack.yml
```

#### 5.5. Download FSxN dashboards and import into Grafana container:
The following commands will download the FSxN designed dashboards from this repo and replace the default Grafana dashboards with them:
```yaml
wget -q https://raw.githubusercontent.com/NetApp/FSx-ONTAP-monitoring/main/Grafana-Prometheus-FSx/fsx_dashboards.zip
unzip fsx_dashboards.zip
rm -rf grafana/dashboards
mv dashboards grafana/dashboards
```

#### 5.6. Configure Prometheus to use yet-another-cloudwatch-exporter (yace) to gather AWS FSxN metrics
AWS has useful metrics regarding the FSxN file system that ONTAP doesn't provide. Therefore, it is recommended to install
an exporter that will retrieve these metrics. The following steps show how to install a recommended exporter.

##### 5.6.1 Create the yace configuration file.
Run the following command to create the configuration file `yace-config.yaml` for YACE:
```yaml
cat <<EOF > yace-config.yaml
apiVersion: v1alpha1
sts-region: us-west-2
discovery:
  jobs:
    - type: AWS/FSx
      regions: [us-west-2]
      period: 300
      length: 300
      metrics:
        - name: DiskReadOperations
          statistics: [Average]
        - name: DiskWriteOperations
          statistics: [Average]
        - name: DiskReadBytes
          statistics: [Average]
        - name: DiskWriteBytes
          statistics: [Average]
        - name: DiskIopsUtilization
          statistics: [Average]
        - name: NetworkThroughputUtilization
          statistics: [Average]
        - name: FileServerDiskThroughputUtilization
          statistics: [Average]
        - name: CPUUtilization
          statistics: [Average]
EOF
```
Don't worry about the `sts-region` and `regions` values, they will be updated later by the `update_clusters.sh` script.

##### 5.6.2 Add Yet-Another-CloudWatch-Exporter to harvest-compose.yml
Run the following command to concatenate the required configuration to the harvest-compose.yml configuration file:
```text
cat <<EOF >> harvest-compose.yml
  yace:
    image: quay.io/prometheuscommunity/yet-another-cloudwatch-exporter:latest
    container_name: yace
    restart: always
    expose:
      - 8080
    volumes:
      - ./yace-config.yaml:/tmp/config.yml
      - $HOME/.aws:/exporter/.aws:ro
    command:
      - -listen-address=:8080
      - -config.file=/tmp/config.yml
    networks:
      - backend
EOF
```

##### 5.6.3. Add Yet-Another-CloudWatch-Exporter target to prometheus.yml:
Run the following command to concatenate the required configuration to the prometheus.yml configuration file:
```yaml
cat <<EOF >> container/prometheus/prometheus.yml
- job_name: 'yace'
  static_configs:
    - targets: ['yace:8080']
EOF
```

#### 6. Add the systems you want to monitor to the Harvest configuration files
Since there are multiple files you have to update to add, or remove, a file system
from the Harvest and Prometheus configuration, a convenience script that does
all that work for you was created. You can download it from this repo here: [update_clusters.sh](update_clusters.sh).

##### 6.1 Download the update_clusters.sh script
You can download the script using the following command:
```sh
wget -q https://raw.githubusercontent.com/NetApp/FSx-ONTAP-monitoring/main/Grafana-Prometheus-FSx/Monitor-FSxN-with-Harvest-on-EC2/update_clusters.sh
```
Give it execute permissions:
```sh
chmod +x update_clusters.sh
```

##### 6.2 Update the list of file system to be monitored
The update_clusters.sh script depends on the `input.txt` file to know which systems you want to monitor. The format of the file is as follows:
```
<filesystem_name>,<managment_ip>,<secret_ARN>,<region>
```
Where:
- `<filesystem_name>`: The name of the FSx for NetApp ONTAP file system. **Cannot contain spaces**.
- `<management_ip>`: The IP address of the cluster management endpoint of the FSx for NetApp ONTAP file system.
- `<secret_ARN>`: The ARN of the AWS Secrets Manager secret that contains the credentials to use.
- `<region>`: The AWS region where the FSx for NetApp ONTAP file system is located.

Note that blank lines, and lines starting with `#`, are ignored.

##### 6.3 Run the update_clusters.sh script
Once you have create the `input.txt` file run the `update_clusters.sh` script:
```sh
./update_clusters.sh
```

#### 7. Bring Everything Up

```sh
docker-compose -f prom-stack.yml -f harvest-compose.yml up -d --remove-orphans
```

After bringing up the prom-stack.yml compose file, you can access Grafana at 
`http://IP_OF_EC2_INSTANCE:3000`.

You will be prompted to create a new password the first time you log in. Grafana's default credentials are:
```
username: admin
password: admin
```

## Updating the file systems to monitor

If later you decide you want to add, or remove, a file system from the list of systems to be
monitored, you can simply update the `input.txt` file and run the `update_clusters.sh` script again.
This will update the Harvest and Prometheus configuration files accordingly and restart the
monitoring containers.

## Author Information

This repository is maintained by the contributors listed on [GitHub](https://github.com/NetApp/FSx-ONTAP-monitoring/graphs/contributors).

## License

Licensed under the Apache License, Version 2.0 (the "License").

You may obtain a copy of the License at [apache.org/licenses/LICENSE-2.0](http://www.apache.org/licenses/LICENSE-2.0).

Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an _"AS IS"_ basis, without WARRANTIES or conditions of any kind, either express or implied.

See the License for the specific language governing permissions and limitations under the License.

© 2025 NetApp, Inc. All Rights Reserved.
