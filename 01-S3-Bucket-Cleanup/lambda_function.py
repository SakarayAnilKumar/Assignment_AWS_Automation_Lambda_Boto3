import datetime
import boto3
from botocore.exceptions import ClientError

# Replace with your actual S3 bucket name
BUCKET_NAME = "anil-aws-assignment-boto3" 

def lambda_handler(event, context):
    # Initialize the low-level S3 client interface
    s3_client = boto3.client('s3')
    
    # Calculate the cutoff date (30 days ago)
    cutoff_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
    
    # Create an explicit paginator for listing objects
    paginator = s3_client.get_paginator('list_objects_v2')
    
    deleted_count = 0
    pages_processed = 0
    
    try:
        print(f"Starting paginated scan for bucket: {BUCKET_NAME}")
        
        # Paginate through the bucket 1,000 objects at a time
        page_iterator = paginator.paginate(Bucket=BUCKET_NAME)
        
        for page in page_iterator:
            pages_processed += 1
            # Check if the current page contains any objects
            if 'Contents' not in page:
                continue
                
            objects_to_delete = []
            
            # Filter objects on the current page that match the age criteria
            for obj in page['Contents']:
                if obj['LastModified'] < cutoff_date:
                    objects_to_delete.append({'Key': obj['Key']})
                    print(f"Queued for deletion: {obj['Key']} (Modified: {obj['LastModified']})")
            
            # Batch delete the expired objects from this page (S3 allows up to 1,000 deletes per request)
            if objects_to_delete:
                s3_client.delete_objects(
                    Bucket=BUCKET_NAME,
                    Delete={'Objects': objects_to_delete}
                )
                deleted_count += len(objects_to_delete)
                
        print(f"Scan complete. Processed {pages_processed} pages.")
        return {
            'statusCode': 200,
            'body': f"Successfully processed {pages_processed} pages and deleted {deleted_count} objects older than 30 days."
        }
        
    except ClientError as e:
        print(f"Error executing paginated deletion: {e}")
        return {
            'statusCode': 500,
            'body': f"Error: {str(e)}"
        }
