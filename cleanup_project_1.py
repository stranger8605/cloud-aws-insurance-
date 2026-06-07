import os
import sys
import json
import time
import boto3

STATE_FILE = "project1_state.json"

def main():
    print("="*60)
    print("         CLEANUP: PROJECT 1 AWS RESOURCES")
    print("="*60)

    if not os.path.exists(STATE_FILE):
        print(f"[!] State file '{STATE_FILE}' not found.")
        print("    If resources were created manually, please delete them via the AWS Console.")
        sys.exit(0)

    # Read state
    try:
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
    except Exception as e:
        print(f"[Error] Failed to read state file '{STATE_FILE}': {e}")
        sys.exit(1)

    instance_id = state.get("instance_id")
    sg_id = state.get("security_group_id")
    key_name = state.get("key_name")
    sns_topic_arn = state.get("sns_topic_arn")
    alarm_name = state.get("alarm_name")
    region = state.get("region", "us-east-1")

    print(f"[*] Region: {region}")

    # Initialize AWS clients
    try:
        ec2_client = boto3.client('ec2', region_name=region)
        cw_client = boto3.client('cloudwatch', region_name=region)
        sns_client = boto3.client('sns', region_name=region)
    except Exception as e:
        print(f"[Error] Failed to initialize AWS clients: {e}")
        sys.exit(1)

    # 1. Delete CloudWatch Alarm
    if alarm_name:
        print(f"[*] Deleting CloudWatch Alarm: {alarm_name}")
        try:
            cw_client.delete_alarms(AlarmNames=[alarm_name])
            print("[+] Alarm deleted.")
        except Exception as e:
            print(f"[!] Error deleting alarm: {e}")

    # 2. Delete SNS Topic
    if sns_topic_arn:
        print(f"[*] Deleting SNS Topic: {sns_topic_arn}")
        try:
            sns_client.delete_topic(TopicArn=sns_topic_arn)
            print("[+] SNS Topic deleted.")
        except Exception as e:
            print(f"[!] Error deleting SNS topic: {e}")

    # 3. Terminate EC2 Instance
    if instance_id:
        print(f"[*] Terminating EC2 Instance: {instance_id}")
        try:
            ec2_client.terminate_instances(InstanceIds=[instance_id])
            print("[*] Termination command sent. Waiting for instance to terminate (this may take a couple of minutes)...")
            
            # Wait for instance to terminate
            waiter = ec2_client.get_waiter('instance_terminated')
            waiter.wait(InstanceIds=[instance_id], WaiterConfig={'Delay': 10, 'MaxAttempts': 30})
            print("[+] EC2 Instance terminated successfully.")
        except Exception as e:
            print(f"[!] Error terminating instance: {e}")

    # 4. Delete Security Group
    if sg_id:
        # Give AWS a few seconds extra to detach interfaces
        time.sleep(5)
        print(f"[*] Deleting Security Group ID: {sg_id}")
        try:
            ec2_client.delete_security_group(GroupId=sg_id)
            print("[+] Security Group deleted.")
        except Exception as e:
            print(f"[!] Error deleting Security Group (retrying in 10s): {e}")
            time.sleep(10)
            try:
                ec2_client.delete_security_group(GroupId=sg_id)
                print("[+] Security Group deleted on retry.")
            except Exception as e2:
                print(f"[!] Failed to delete Security Group again. Please check manually in console: {e2}")

    # 5. Delete Key Pair
    if key_name:
        print(f"[*] Deleting AWS Key Pair: {key_name}")
        try:
            ec2_client.delete_key_pair(KeyName=key_name)
            print("[+] AWS Key Pair deleted.")
        except Exception as e:
            print(f"[!] Error deleting key pair from AWS: {e}")

        pem_file = f"{key_name}.pem"
        if os.path.exists(pem_file):
            print(f"[*] Deleting local private key file: {pem_file}")
            try:
                os.remove(pem_file)
                print("[+] Local PEM file deleted.")
            except Exception as e:
                print(f"[!] Error deleting local PEM file: {e}")

    # 6. Clean up state file
    try:
        os.remove(STATE_FILE)
        print(f"[+] Deleted local state file '{STATE_FILE}'.")
    except Exception as e:
        print(f"[!] Error deleting state file: {e}")

    print("\n" + "="*60)
    print("             CLEANUP PROCESS COMPLETED!")
    print("="*60)

if __name__ == "__main__":
    main()
