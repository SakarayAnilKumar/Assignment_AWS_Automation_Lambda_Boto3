import json
import os
import boto3
from datetime import datetime, timezone

ec2 = boto3.client('ec2')

def lambda_handler(event, context):
    print("Received EventBridge Event:", json.dumps(event))
    
    # Extract Instance ID from EC2 State-Change Notification
    detail = event.get('detail', {})
    instance_id = detail.get('instance-id')
    state = detail.get('state')
    
    if not instance_id:
        print("Error: Event payload missing 'instance-id'. Skipping.")
        return {'statusCode': 400, 'body': 'Missing instance-id'}
        
    print(f"Processing Instance ID: {instance_id} | State: {state}")
    
    # Metadata Calculations
    current_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    # Phase 1: Hardcoded Owner Username (For testing)
    owner_username = os.environ.get('HARDCODED_OWNER', 'john.doe@company.com')
    
    tags_to_apply = [
        {'Key': 'LaunchDate', 'Value': current_date},
        {'Key': 'Owner', 'Value': owner_username},
        {'Key': 'AutoTagged', 'Value': 'True'}
    ]
    
    try:
        ec2.create_tags(
            Resources=[instance_id],
            Tags=tags_to_apply
        )
        msg = f"SUCCESS: Tagged instance {instance_id} | Owner: {owner_username}"
        print(msg)
        return {'statusCode': 200, 'body': msg}
    except Exception as e:
        error_msg = f"ERROR: Failed to tag instance {instance_id}: {str(e)}"
        print(error_msg)
        raise e