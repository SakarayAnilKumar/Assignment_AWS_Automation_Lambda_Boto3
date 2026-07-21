import os
import boto3
from datetime import datetime, timezone, timedelta

ec2 = boto3.client('ec2')

RETENTION_DAYS = 30
TAG_KEY = 'CreatedBy'
TAG_VALUE = 'Lambda-Backup'

def lambda_handler(event, context):
    now = datetime.now(timezone.utc)
    cutoff_date = now - timedelta(days=RETENTION_DAYS)
    
    print(f"Starting snapshot execution. Retention cutoff date: {cutoff_date.isoformat()}")

    # 1. Discover all EBS volumes in the current region
    paginator = ec2.get_paginator('describe_volumes')
    volumes = []
    for page in paginator.paginate():
        for vol in page.get('Volumes', []):
            volumes.append(vol['VolumeId'])

    if not volumes:
        print("No EBS volumes found in this region.")
        return {'statusCode': 200, 'body': 'No volumes found.'}

    summary = []

    # 2. Process each volume: CREATE FIRST -> DELETE SECOND
    for volume_id in volumes:
        print(f"\n--- Processing Volume: {volume_id} ---")

        # STEP A: Create the new snapshot FIRST
        print(f"Creating latest snapshot for volume {volume_id}...")
        snap_res = ec2.create_snapshot(
            VolumeId=volume_id,
            Description=f"Automated backup for {volume_id} on {now.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            TagSpecifications=[
                {
                    'ResourceType': 'snapshot',
                    'Tags': [
                        {'Key': TAG_KEY, 'Value': TAG_VALUE},
                        {'Key': 'Name', 'Value': f"Backup-{volume_id}-{now.strftime('%Y%m%d-%H%M%S')}"}
                    ]
                }
            ]
        )
        new_snap_id = snap_res['SnapshotId']
        print(f"Successfully created new Snapshot ID: {new_snap_id}")

        # STEP B: Find and delete expired snapshots AFTER creation succeeds
        snapshots_response = ec2.describe_snapshots(
            OwnerIds=['self'],
            Filters=[
                {'Name': f'tag:{TAG_KEY}', 'Values': [TAG_VALUE]},
                {'Name': 'volume-id', 'Values': [volume_id]}
            ]
        )
        
        deleted_ids = []
        for snapshot in snapshots_response.get('Snapshots', []):
            snapshot_id = snapshot['SnapshotId']
            start_time = snapshot['StartTime']

            # Safety check: ignore the snapshot we just created
            if snapshot_id == new_snap_id:
                continue

            # Delete if older than retention cutoff
            if start_time < cutoff_date:
                print(f"Deleting expired snapshot {snapshot_id} (Created: {start_time})...")
                ec2.delete_snapshot(SnapshotId=snapshot_id)
                deleted_ids.append(snapshot_id)

        summary.append({
            'volume_id': volume_id,
            'created_snapshot': new_snap_id,
            'deleted_snapshots': deleted_ids
        })

    print("\n=== EXECUTION SUMMARY ===")
    print(summary)

    return {
        'statusCode': 200,
        'body': summary
    }