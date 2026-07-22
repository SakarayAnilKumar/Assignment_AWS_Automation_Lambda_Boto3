import os
from datetime import datetime, timedelta
import boto3


# Initialize AWS SDK clients outside the handler for reuse
ce_client = boto3.client('ce')
sns_client = boto3.client('sns')

def get_month_to_date_range():
    """Returns Start and End date strings formatted for Cost Explorer API."""
    today = datetime.utcnow().date()
    start_date = today.replace(day=1).strftime('%Y-%m-%d')
    
    # Cost Explorer 'End' is exclusive and must be strictly after 'Start'
    if today.day == 1:
        end_date = (today + timedelta(days=1)).strftime('%Y-%m-%d')
    else:
        end_date = today.strftime('%Y-%m-%d')
        
    return start_date, end_date

def lambda_handler(event, context):
    topic_arn = 'arn:aws:sns:us-east-1:316412036553:aws-cost-alert'
    threshold = float(os.environ.get('COST_THRESHOLD', '50.00'))
    
    start_date, end_date = get_month_to_date_range()
    
    print(f"Querying Cost Explorer MTD spend from {start_date} to {end_date}")
    
    try:
        response = ce_client.get_cost_and_usage(
            TimePeriod={'Start': start_date, 'End': end_date},
            Granularity='MONTHLY',
            Metrics=['UnblendedCost']
        )
        
        # Extract total unblended cost amount
        results = response.get('ResultsByTime', [])
        if not results:
            print("No cost data returned from Cost Explorer.")
            return {"statusCode": 200, "body": "No data available"}
            
        current_spend_str = results[0]['Total']['UnblendedCost']['Amount']
        currency = results[0]['Total']['UnblendedCost']['Unit']
        current_spend = float(current_spend_str)
        
        print(f"Current MTD AWS Spend: {current_spend:.2f} {currency} (Threshold: {threshold:.2f} {currency})")
        
        # Check threshold condition
        if current_spend >= threshold:
            message = (
                f"⚠️ AWS COST ALERT\n\n"
                f"Your Month-To-Date (MTD) AWS spend has exceeded your defined threshold.\n\n"
                f"• Current Spend: ${current_spend:,.2f} {currency}\n"
                f"• Threshold: ${threshold:,.2f} {currency}\n"
                f"• Period: {start_date} to {end_date}\n\n"
                f"Please review your AWS Billing Dashboard to analyze usage."
            )
            
            sns_client.publish(
                TopicArn=topic_arn,
                Subject=f"AWS Cost Alert: Spend exceeded ${threshold:.2f}",
                Message=message
            )
            print("Notification successfully sent to SNS.")
        else:
            print("Spend is within budget limit. No alert required.")
            
        return {
            "statusCode": 200,
            "body": f"Processed successfully. Current Spend: ${current_spend:.2f}"
        }

    except Exception as e:
        print(f"Error querying cost or publishing alert: {str(e)}", exc_info=True)
        raise e