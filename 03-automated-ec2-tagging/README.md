# AWS EC2 Automated Resource Tagging Engine
## Technical Blueprint, EventBridge Configuration, CloudTrail Parsing & Troubleshooting Guide

---

## Objective
The primary objective of this system is to automatically tag newly launched Amazon EC2 instances upon entering the `running` state. This ensures strict resource tracking, granular cost allocation, ownership attribution, and operational compliance across AWS environments.

---

## System Architecture Overview

```text
  ┌──────────────────┐        State Change (running)        ┌──────────────────┐
  │   EC2 Instance   ├─────────────────────────────────────►│ Amazon EventBridge│
  └──────────────────┘                                      └────────┬─────────┘
                                                                     │ Triggers Target
                                                                     ▼
  ┌──────────────────┐           Applies Tags               ┌──────────────────┐
  │  Amazon EC2 API  │◄─────────────────────────────────────┤    AWS Lambda    │
  └──────────────────┘                                      └────────┬─────────┘
                                                                     │ Query Identity (Bonus)
                                                                     ▼
                                                            ┌──────────────────┐
                                                            │  AWS CloudTrail  │
                                                            └──────────────────┘
```

---

## 1. Lambda IAM Role & Security Policy

To grant the Lambda function minimum required privileges for resource tagging and identity lookup, attach an IAM execution role containing the policy described below.

### Policy Parameter Description
* **`ec2:CreateTags`**: Grants permission to attach key-value tags to EC2 resources (`Resource: "*"`).
* **`ec2:DescribeInstances`**: Grants permission to read instance metadata and confirm state.
* **`cloudtrail:LookupEvents`**: Grants permission to query CloudTrail logs to extract caller identities for automated ownership attribution (Bonus Scenario).
* **`logs:*`**: Grants standard AWS CloudWatch permission to write function output and debugging logs

---

## 2. EventBridge Trigger Rule

Amazon EventBridge monitors infrastructure events and routes matching payloads to the target Lambda function.

### Event Pattern Breakdown
* **`source`**: Restricted to `["aws.ec2"]` to filter events originating from Amazon Elastic Compute Cloud.
* **`detail-type`**: Set to `["EC2 Instance State-change Notification"]` to intercept lifecycle updates.
* **`detail.state`**: Filtered strictly to `["running"]` so tagging executes only after instance initialization completes.

### Event Pattern Configuration (JSON Structure)

> **Target Assignment:** In the EventBridge console, set the target of this rule to point directly to the deployed **Auto-Tagging Lambda Function**.

---

## 3. Lambda Function Core Logic (Boto3)

The AWS Lambda function extracts event details, calculates metadata parameters, and applies standard resource tags.

### Functional Breakdown & Logic Description
1. **Event Extraction**: Parses incoming JSON payload from EventBridge to extract the instance identifier from `event['detail']['instance-id']`.
2. **Metadata Calculation**: Calculates the current UTC launch date formatted as `YYYY-MM-DD` and set variables for `Owner` (hardcoded to my user)).
3. **Tag Execution**: Invokes `boto3.client('ec2').create_tags()` to write key-value pairs (`LaunchDate`, `Environment`, `Owner`, `AutoTagged`).
4. **Logging Confirmation**: Outputs structured status messages to CloudWatch for operational tracking and verification.

---

## 4. End-to-End Testing & Verification

Follow this workflow to validate rule matching and successful tag application.

### Step 1: Launch EC2 Instance
* Open the **AWS Management Console** -> **EC2 Services**.
* Launch a standard Linux instance (e.g., `t3.micro`). Leave the initial tags blank.

### Step 2: Confirm Event & Execution
* Wait approximately 10 to 30 seconds for the instance to transition to `running`.
* Open **CloudWatch Console** -> **Log Groups** -> `/aws/lambda/<your-function-name>`.
* Open the latest log stream and locate the confirmation message:
  `SUCCESS: Successfully tagged instance i-xxxxxxxxxxxxxxxxx`

### Step 3: Inspect Resource Tags
* Return to the **EC2 Console**, select the newly launched instance, and click the **Tags** tab.
* Confirm that the following tags are present:

| Tag Key | Expected Value | Description |
| :--- | :--- | :--- |
| **`LaunchDate`** | `2026-07-22` | ISO UTC launch date timestamp |
| **`Owner`** | `DevOps-Team` | Baseline default or parsed identity |
| **`AutoTagged`** | `True` | Governance compliance flag |

---

## 5. Bonus : Automated Identity Extraction via CloudTrail

Automated Identity Extraction or Dynamically parsing the identity of the IAM user or AWS Single Sign-On (SSO) role that launched the instance, rather than relying on hardcoded static owners.

### Dynamic Identity Extraction Method (Boto3 Integration)

```python
import json
import boto3

cloudtrail = boto3.client('cloudtrail')

def parse_user_identity_from_cloudtrail(instance_id):
    """
    Queries CloudTrail LookupEvents for the RunInstances API event matching instance_id.
    Parses IAM users, SSO identities, and Assumed Roles.
    """
    try:
        response = cloudtrail.lookup_events(
            LookupAttributes=[{
                'AttributeKey': 'ResourceName',
                'AttributeValue': instance_id
            }],
            MaxResults=5
        )
        
        for event in response.get('Events', []):
            if event.get('EventName') == 'RunInstances':
                payload = json.loads(event.get('CloudTrailEvent', '{}'))
                user_identity = payload.get('userIdentity', {})
                identity_type = user_identity.get('type')
                
                # Case A: AWS SSO / Assumed Roles
                if identity_type == 'AssumedRole':
                    arn = user_identity.get('arn', '')
                    session_name = arn.split('/')[-1]
                    # Filter out EC2 instance profile execution roles
                    if not session_name.startswith('i-'):
                        return session_name
                
                # Case B: Direct IAM User
                elif identity_type == 'IAMUser':
                    return user_identity.get('userName', 'IAMUser')
                
                # Case C: Federated User
                elif identity_type == 'FederatedUser':
                    principal_id = user_identity.get('principalId', '')
                    return principal_id.split(':')[-1] if ':' in principal_id else principal_id

    except Exception as e:
        print(f"CloudTrail lookup warning: {str(e)}")
        
    return "Unknown-Owner"
```

---

## 6. Troubleshooting: Why `Unknown-Owner` Is Returned & Remediation

### The Root Cause (Timing & Indexing Discrepancy)

When integrating CloudTrail identity lookups with EventBridge State-Change triggers, developers frequently observe that the `Owner` tag defaults to `Unknown-Owner` or `Unknown-User`.

```text
TIMELINE DISCREPANCY:

  Time = 0s                    Time = 2-5s                  Time = 5m - 15m
  ┌─────────────────────┐      ┌──────────────────────┐     ┌──────────────────────┐
  │ EC2 RunInstances    │      │ EventBridge State    │     │ CloudTrail Ingestion │
  │ API Call Executed   │      │ Notification Fires   │     │ & Search Index Sync  │
  └──────────┬──────────┘      └──────────┬───────────┘     └──────────┬───────────┘
             │                            │                            │
             ▼                            ▼                            ▼
  Instance Initialized        Lambda Executes Lookup        Log Indexed & Searchable
                              `cloudtrail.lookup_events()`  `cloudtrail.lookup_events()`
                              Returns: [] (EMPTY)           Returns: RunInstances Event
                              Result: "Unknown-Owner"       Result: User Identity
```

#### Why This Occurs
1. **CloudTrail Indexing Delay**: AWS CloudTrail API events require **5 to 15 minutes** to process, digest, and make searchable via the `cloudtrail:LookupEvents` endpoint.
2. **Instant EventBridge Execution**: EventBridge emits the `EC2 Instance State-change Notification` within **2 to 5 seconds** of an instance reaching `running`.
3. **Payload Absence**: The State-Change notification payload contains infrastructure metadata (`instance-id`, `state`), but **contains zero identity/caller parameters**.
4. **Lookup Failure**: When Lambda queries CloudTrail immediately upon event receipt, CloudTrail has not finished indexing the `RunInstances` API call. The lookup returns an empty list `[]`, falling back to `Unknown-Owner`.

---

### Strategy & Fix Matrix

To eliminate the `Unknown-Owner` issue in production, select one of the following three solutions based on operational trade-offs:

| Remediation Strategy | Architectural Approach | Pros | Cons |
| :--- | :--- | :--- | :--- |
| **Strategy 1: Direct CloudTrail API Event Pattern** | Trigger EventBridge from CloudTrail `RunInstances` API call directly instead of State-Change. | Zero delay; identity payload is natively included in event. | Requires CloudTrail Multi-Region Trail enabled in AWS Account. |
| **Strategy 2: Amazon SQS Delay Queue** | EventBridge routes state notification to SQS with a 10-minute delivery delay before triggering Lambda. | Fully decoupled, cost-efficient, zero idle compute. | Introduces minor architectural complexity (SQS resource). |
| **Strategy 3: Lambda In-Function Retry / Polling** | Lambda polls `cloudtrail:LookupEvents` in a backoff loop (`time.sleep`) until indexed. | No additional AWS resources required. | Increases Lambda execution duration and cost. |

---

### Detailed Code Fixes

#### Fix Option A: EventBridge Rule for CloudTrail API Event (Recommended Zero-Wait Solution)
Modify the EventBridge rule pattern to intercept the CloudTrail API call directly. This guarantees the user identity is present in the payload on invocation.

```json
{
  "source": [
    "aws.ec2"
  ],
  "detail-type": [
    "AWS API Call via CloudTrail"
  ],
  "detail": {
    "eventSource": [
      "ec2.amazonaws.com"
    ],
    "eventName": [
      "RunInstances"
    ]
  }
}
```

#### Fix Option B: Smart Polling Fallback in Lambda Logic
If maintaining the `EC2 Instance State-change Notification` trigger is required, implement a retry loop inside the Lambda lookup logic:

```python
import time

def poll_cloudtrail_for_owner(instance_id, max_retries=6, delay_seconds=30):
    """
    Polls CloudTrail LookupEvents with delay intervals to account for log indexing lag.
    """
    for attempt in range(1, max_retries + 1):
        print(f"Polling CloudTrail for instance {instance_id} (Attempt {attempt}/{max_retries})...")
        owner = parse_user_identity_from_cloudtrail(instance_id)
        
        if owner != "Unknown-Owner":
            print(f"SUCCESS: Identity '{owner}' indexed and retrieved on attempt {attempt}.")
            return owner
            
        if attempt < max_retries:
            time.sleep(delay_seconds)
            
    return "Unknown-Owner"
```
