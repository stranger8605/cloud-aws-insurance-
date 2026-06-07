import os
import sys
import json
import time
import subprocess
from pathlib import Path

# Try importing dependencies, alert the user if they're not ready yet
try:
    import boto3
    import requests
except ImportError:
    print("[!] Required packages (boto3, requests) are not installed or still installing.")
    print("[*] Please wait for the package installer or run: pip install boto3 requests")
    sys.exit(1)

STATE_FILE = "project1_state.json"

def setup_aws_credentials():
    """Ensure AWS credentials are configured. Prompt the user if not."""
    aws_dir = Path.home() / '.aws'
    credentials_path = aws_dir / 'credentials'
    config_path = aws_dir / 'config'

    # Check if credentials file or environment variables exist
    if credentials_path.exists() or os.environ.get('AWS_ACCESS_KEY_ID'):
        print("[*] AWS credentials configuration found.")
        return True

    print("\n" + "="*50)
    print("           AWS CREDENTIALS SETUP")
    print("="*50)
    print("Credentials were not found in standard AWS paths or environment.")
    print("Please enter your credentials to allow this script to deploy resources.")
    print("Your credentials will be stored securely in standard ~/.aws files.")
    print("-"*50)
    
    access_key = input("AWS Access Key ID: ").strip()
    secret_key = input("AWS Secret Access Key: ").strip()
    region = input("AWS Default Region [us-east-1]: ").strip() or 'us-east-1'

    if not access_key or not secret_key:
        print("[Error] Both AWS Access Key ID and Secret Access Key are required to run the automation.")
        return False

    try:
        aws_dir.mkdir(exist_ok=True)
        with open(credentials_path, 'w') as f:
            f.write(f"[default]\naws_access_key_id = {access_key}\naws_secret_access_key = {secret_key}\n")
        with open(config_path, 'w') as f:
            f.write(f"[default]\nregion = {region}\n")
        print(f"[+] Credentials successfully written to: {credentials_path}")
        return True
    except Exception as e:
        print(f"[Error] Failed to write AWS credentials: {e}")
        return False

def get_public_ip():
    """Retrieve the user's public IP address for restricting SSH access."""
    print("[*] Detecting your local public IP address...")
    try:
        response = requests.get('https://api.ipify.org', timeout=10)
        if response.status_code == 200:
            ip = response.text.strip()
            print(f"[+] Detected Public IP: {ip}")
            return ip
    except Exception as e:
        print(f"[!] Warning: Auto-detection of public IP failed: {e}")
    
    # Prompt user as fallback
    while True:
        ip = input("Please enter your current public IP address (e.g., 203.0.113.50): ").strip()
        if ip:
            return ip

def get_latest_ami(ec2_client):
    """Find the latest Amazon Linux 2023 AMI in the current region."""
    print("[*] Querying latest Amazon Linux 2023 AMI...")
    try:
        response = ec2_client.describe_images(
            Filters=[
                {'Name': 'name', 'Values': ['al2023-ami-2023.*-kernel-6.1-x86_64']},
                {'Name': 'state', 'Values': ['available']},
                {'Name': 'image-type', 'Values': ['machine']}
            ],
            Owners=['amazon']
        )
        images = response['Images']
        images.sort(key=lambda x: x['CreationDate'], reverse=True)
        if images:
            print(f"[+] Selected AMI: {images[0]['ImageId']} ({images[0]['Name']})")
            return images[0]['ImageId']
    except Exception as e:
        print(f"[!] Error querying Amazon Linux 2023 AMI: {e}")

    # Fallback to Amazon Linux 2
    print("[*] Searching for Amazon Linux 2 AMI as fallback...")
    try:
        response = ec2_client.describe_images(
            Filters=[
                {'Name': 'name', 'Values': ['amzn2-ami-hvm-2.0.*-x86_64-gp2']},
                {'Name': 'state', 'Values': ['available']}
            ],
            Owners=['amazon']
        )
        images = response['Images']
        images.sort(key=lambda x: x['CreationDate'], reverse=True)
        if images:
            print(f"[+] Selected AMI (Fallback): {images[0]['ImageId']} ({images[0]['Name']})")
            return images[0]['ImageId']
    except Exception as e:
        print(f"[!] Fallback query failed: {e}")

    # Ultimate hardcoded fallback for common regions
    region = ec2_client.meta.region_name
    common_amis = {
        'us-east-1': 'ami-0c55b159cbfafe1f0', # Amazon Linux 2
        'us-east-2': 'ami-00db8575f3e09d05e',
        'us-west-2': 'ami-03d5c48c0897ae3e5',
        'ap-south-1': 'ami-022d03f649d12a49d'
    }
    fallback_ami = common_amis.get(region, 'ami-0c55b159cbfafe1f0')
    print(f"[!] Using hardcoded default AMI for region {region}: {fallback_ami}")
    return fallback_ami

def setup_key_pair(ec2_client, key_name="project1-key"):
    """Create EC2 key pair and set permissions locally."""
    pem_file = f"{key_name}.pem"
    
    # Check if key pair already exists in AWS
    try:
        ec2_client.describe_key_pairs(KeyNames=[key_name])
        print(f"[*] AWS Key Pair '{key_name}' already exists.")
        if os.path.exists(pem_file):
            print(f"[*] Local PEM file '{pem_file}' already exists.")
            return True
        else:
            print(f"[!] Key Pair exists in AWS but local PEM file '{pem_file}' is missing!")
            ans = input("Recreate it? This will delete the key pair in AWS first (y/n): ").strip().lower()
            if ans == 'y':
                print(f"[+] Deleting old key pair from AWS...")
                ec2_client.delete_key_pair(KeyName=key_name)
            else:
                print("[!] Using existing key pair. Please ensure you have the PEM file.")
                return False
    except ec2_client.exceptions.ClientError as e:
        if 'InvalidKeyPair.NotFound' not in str(e):
            raise e

    print(f"[+] Creating Key Pair '{key_name}' in AWS...")
    response = ec2_client.create_key_pair(KeyName=key_name)
    key_material = response['KeyMaterial']

    # Write local file
    with open(pem_file, 'w') as f:
        f.write(key_material)
    print(f"[+] Private key saved to: {os.path.abspath(pem_file)}")

    # Restrict permissions for SSH client on Windows
    try:
        print("[*] Configuring secure file permissions for the private key...")
        # Disable permission inheritance
        subprocess.run(f'icacls.exe "{pem_file}" /inheritance:r', shell=True, check=True, stdout=subprocess.DEVNULL)
        # Grant Read permission to current user only
        username = os.getlogin()
        subprocess.run(f'icacls.exe "{pem_file}" /grant:r "{username}:R"', shell=True, check=True, stdout=subprocess.DEVNULL)
        print(f"[+] Permissions updated: Only '{username}' has Read access to '{pem_file}'.")
    except Exception as ex:
        print(f"[!] Warning: Could not secure key permissions automatically: {ex}")
        print("    If SSH complains about permissions, restrict the PEM file's security settings manually.")

    return True

def setup_security_group(ec2_client, ip_address, sg_name="project1-security-group"):
    """Create security group and configure inbound SSH restricted to user IP."""
    try:
        response = ec2_client.describe_security_groups(GroupNames=[sg_name])
        sg_id = response['SecurityGroups'][0]['GroupId']
        print(f"[*] Security Group '{sg_name}' already exists with ID: {sg_id}")
        return sg_id
    except ec2_client.exceptions.ClientError as e:
        if 'InvalidGroup.NotFound' not in str(e):
            raise e

    # Find Default VPC
    vpcs = ec2_client.describe_vpcs(Filters=[{'Name': 'isDefault', 'Values': ['true']}])
    if not vpcs['Vpcs']:
        # Fetch any VPC if default is not available
        vpcs = ec2_client.describe_vpcs()
    
    vpc_id = vpcs['Vpcs'][0]['VpcId']
    print(f"[+] Creating Security Group '{sg_name}' in VPC {vpc_id}...")
    
    response = ec2_client.create_security_group(
        GroupName=sg_name,
        Description="Security group for Project 1 - allows SSH from my IP only",
        VpcId=vpc_id
    )
    sg_id = response['GroupId']
    
    # Authorize SSH inbound rule
    cidr = f"{ip_address}/32"
    print(f"[+] Configuring Inbound Rule: Allow SSH (Port 22) from {cidr}...")
    ec2_client.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[
            {
                'IpProtocol': 'tcp',
                'FromPort': 22,
                'ToPort': 22,
                'IpRanges': [{'CidrIp': cidr, 'Description': 'Owner Public IP SSH Access'}]
            }
        ]
    )
    print("[+] Inbound rules configured successfully.")
    return sg_id

def launch_ec2_instance(ec2_client, key_name, sg_id, ami_id):
    """Launch EC2 instance with OS security hardening script injected as User Data."""
    # Hardening User Data Script
    user_data_script = r"""#!/bin/bash
# Exercise 3: Update and Secure Your Instance
echo "[*] Starting system update and security hardening..."

# 1. Update and Upgrade packages
yum update -y
yum upgrade -y

# 3. Create a new user
adduser newuser
# 4. Grant new user sudo privileges
usermod -aG wheel newuser

# 5. Secure SSH Access
# Disable root login
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
# Disable password authentication
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config

# Restart SSH service
systemctl restart sshd
echo "[+] System update and hardening complete."
"""

    print("[*] Launching EC2 instance...")
    response = ec2_client.run_instances(
        ImageId=ami_id,
        MinCount=1,
        MaxCount=1,
        InstanceType='t2.micro',
        KeyName=key_name,
        SecurityGroupIds=[sg_id],
        UserData=user_data_script,
        TagSpecifications=[
            {
                'ResourceType': 'instance',
                'Tags': [{'Key': 'Name', 'Value': 'Project1-Secure-EC2'}]
            }
        ]
    )
    instance_id = response['Instances'][0]['InstanceId']
    print(f"[+] EC2 Instance launched successfully: {instance_id}")
    return instance_id

def setup_cloudwatch_monitoring(cw_client, sns_client, instance_id, region):
    """Set up SNS Topic and CloudWatch CPU Alarm."""
    print("[*] Provisioning SNS Topic 'Project1-Alerts'...")
    sns_response = sns_client.create_topic(Name="Project1-Alerts")
    topic_arn = sns_response['TopicArn']
    print(f"[+] SNS Topic ARN: {topic_arn}")

    print("\n" + "-"*50)
    email = input("Enter email address to subscribe to CPU utilization alerts (Press Enter to skip): ").strip()
    if email:
        sns_client.subscribe(
            TopicArn=topic_arn,
            Protocol='email',
            Endpoint=email
        )
        print(f"[+] Subscription invitation sent to: {email}")
        print("[!] Note: You must open the email received and click 'Confirm Subscription' to receive alerts.")
    print("-"*50)

    alarm_name = "Project1-CPU-Utilization-Alarm"
    print(f"[+] Creating CloudWatch Alarm '{alarm_name}' (CPU > 80% for 5 mins)...")
    cw_client.put_metric_alarm(
        AlarmName=alarm_name,
        ComparisonOperator='GreaterThanThreshold',
        EvaluationPeriods=1,
        MetricName='CPUUtilization',
        Namespace='AWS/EC2',
        Period=300,
        Statistic='Average',
        Threshold=80.0,
        ActionsEnabled=True,
        AlarmActions=[topic_arn],
        AlarmDescription='Alarm if instance CPU utilization exceeds 80% for 5 minutes',
        Dimensions=[
            {
                'Name': 'InstanceId',
                'Value': instance_id
            },
        ],
        Unit='Percent'
    )
    print("[+] CloudWatch Alarm created successfully.")
    return alarm_name, topic_arn

def save_state(state):
    """Save resource information for the cleanup script."""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)
    print(f"[+] Resource metadata state saved to '{STATE_FILE}' for automated cleanup.")

def main():
    print("="*60)
    print("      AUTOMATED LAB: AWS EC2 SECURITY HARDENING")
    print("="*60)

    if not setup_aws_credentials():
        print("[!] Aborting setup: No valid credentials.")
        return

    # Initialize boto3 clients
    try:
        ec2_client = boto3.client('ec2')
        cw_client = boto3.client('cloudwatch')
        sns_client = boto3.client('sns')
        # Check connection by calling describe_regions
        ec2_client.describe_regions()
    except Exception as e:
        print(f"[Error] Failed to connect to AWS: {e}")
        print("Please check your AWS Access Key, Secret Key, and network connectivity.")
        return

    region = ec2_client.meta.region_name
    print(f"[*] AWS Session established successfully in Region: {region}")

    # 1. Get user's public IP
    user_ip = get_public_ip()

    # 2. Get latest AMI
    ami_id = get_latest_ami(ec2_client)

    # 3. Create Key Pair
    key_name = "project1-key"
    if not setup_key_pair(ec2_client, key_name):
        print("[!] Aborting due to key pair configuration issue.")
        return

    # 4. Create Security Group
    sg_id = setup_security_group(ec2_client, user_ip)

    # 5. Launch EC2 Instance with User Data security hardening
    instance_id = launch_ec2_instance(ec2_client, key_name, sg_id, ami_id)

    # 6. Set up Monitoring (CloudWatch and SNS)
    alarm_name, topic_arn = setup_cloudwatch_monitoring(cw_client, sns_client, instance_id, region)

    # 7. Save State
    state = {
        "instance_id": instance_id,
        "security_group_id": sg_id,
        "key_name": key_name,
        "sns_topic_arn": topic_arn,
        "alarm_name": alarm_name,
        "region": region
    }
    save_state(state)

    # 8. Wait for instance to get Public DNS
    print("\n[*] Waiting for EC2 Instance to complete startup...")
    try:
        # Wait up to 2 minutes
        waiter = ec2_client.get_waiter('instance_running')
        waiter.wait(InstanceIds=[instance_id], WaiterConfig={'Delay': 5, 'MaxAttempts': 24})
        
        response = ec2_client.describe_instances(InstanceIds=[instance_id])
        instance = response['Reservations'][0]['Instances'][0]
        public_dns = instance.get('PublicDnsName')
        public_ip = instance.get('PublicIpAddress')
        
        print("\n" + "="*60)
        print("                 DEPLOYMENT SUCCESSFUL!")
        print("="*60)
        print(f"Instance ID:          {instance_id}")
        print(f"Public IP:            {public_ip}")
        print(f"Public DNS:           {public_dns}")
        print(f"Key Pair Location:    {os.path.abspath(key_name + '.pem')}")
        print("-"*60)
        print("HOW TO CONNECT:")
        print(f"  ssh -i \"{key_name}.pem\" ec2-user@{public_ip}")
        print("\nVERIFY OS SECURITY HARDENING:")
        print("  1. The User Data script automatically updates system packages (yum update).")
        print("  2. It creates a new user named 'newuser' with administrative (sudo) privileges.")
        print("     Verify by running: ssh -i \"{key_name}.pem\" ec2-user@{public_ip} \"id newuser\"")
        print("  3. SSH daemon configuration is secured:")
        print("     - Root login is disabled.")
        print("     - Password authentication is disabled (only SSH keys allowed).")
        print("     Verify by checking sshd settings: cat /etc/ssh/sshd_config | grep -E 'PermitRootLogin|PasswordAuthentication'")
        print("\nCLEANUP INFORMATION:")
        print("  Once you are done with the lab, run the cleanup script to avoid charges:")
        print("  python cleanup_project_1.py")
        print("="*60)

    except Exception as e:
        print(f"[!] Warning: Waiter or DNS retrieval encountered an error: {e}")
        print(f"    Please manually check the EC2 Dashboard for Instance ID: {instance_id}")

if __name__ == "__main__":
    main()
