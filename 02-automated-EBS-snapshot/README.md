# Automated EBS Volume Backup and Retention Lifecycle Documentation

## Section 1: Executive Summary & Overview

### 1.1 Objective
This document details the engineering specifications, IAM policy descriptions, implementation logic, and scheduling configurations for an automated, serverless Amazon Elastic Block Store (EBS) snapshot backup and lifecycle retention system. 

### 1.2 System Purpose & Operational Scope
In enterprise AWS environments, maintaining consistent data backups while strictly controlling snapshot storage costs is essential. This solution provides:
* **Region-wide Volume Coverage:** Automatically discovers all EBS volumes within an AWS region without requiring hardcoded volume IDs.
* **Fail-Safe Lifecycle Order:** Creates a new snapshot *before* evaluating and deleting expired snapshots to prevent data gaps during failure scenarios.
* **Automated Retention Management:** Automatically purges snapshots created by this automation that exceed a configurable retention threshold (default: 30 days).
* **Tag-Based Governance:** Uses specific resource tags (`CreatedBy=Lambda-Backup`) to prevent accidental deletion of manual or third-party backups.

---

## Section 2: Architecture & Operational Workflow

### 2.1 Technical Architecture
The system utilizes a fully serverless, event-driven pattern using native AWS services:

```text
  ┌────────────────────────────────────────────────────────┐
  │                 Amazon EventBridge                     │
  │      (Cron Schedule / EventBridge Scheduler)           │
  └───────────────────────────┬────────────────────────────┘
                              │ Triggers (lambda:InvokeFunction)
                              ▼
  ┌────────────────────────────────────────────────────────┐
  │                 AWS Lambda Function                    │
  │               (Python 3.12 Runtime)                    │
  └───────┬───────────────────┬───────────────────┬────────┘
          │                   │                   │
   1. Discover         2. Create First     3. Delete Expired
          │                   │                   │
          ▼                   ▼                   ▼
  ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
  │   EBS Volume  │   │  EC2 Snapshot │   │ Old Snapshots │
  │  (Describe)   │   │ (Create & Tag)│   │ (> Retention) │
  └───────────────┘   └───────────────┘   └───────────────┘
```

### 2.2 Sequence of Execution
1. **Trigger Phase:** Amazon EventBridge executes the Lambda function based on a configured cron expression.
2. **Discovery Phase:** Lambda executes `ec2:DescribeVolumes` with pagination to collect all active volume IDs in the region.
3. **Snapshot Creation Phase (Create First):**
   * For each volume, Lambda calls `ec2:CreateSnapshot`.
   * Tags the new snapshot with `CreatedBy = Lambda-Backup` and `Name = Backup-{volume_id}-{timestamp}`.
4. **Retention Evaluation & Cleanup Phase (Delete Second):**
   * Lambda calls `ec2:DescribeSnapshots` filtering by `OwnerIds=['self']`, `volume-id`, and `tag:CreatedBy=Lambda-Backup`.
   * Ignores the newly created snapshot ID.
   * Compares each remaining snapshot's `StartTime` against the calculated cutoff timestamp (`now - RETENTION_DAYS`).
   * Calls `ec2:DeleteSnapshot` on any snapshot older than the cutoff threshold.
5. **Reporting Phase:** Emits execution summaries to Amazon CloudWatch Logs.

---

## Section 3: Identity & Access Management (IAM) Specifications

To adhere to the principle of least privilege, the Lambda execution role and resource policies are scoped strictly to required actions and resources.

### 3.1 Lambda Execution Role Policy Description
The Lambda execution role (`EBS-Backup-Lambda-Role`) is granted permissions divided into two functional statements:

* **CloudWatch Logging Capabilities:**
  * **Actions Allowed:** Grants permissions to create log groups (`logs:CreateLogGroup`), create log streams (`logs:CreateLogStream`), and stream execution logs (`logs:PutLogEvents`).
  * **Resource Scope:** Restricted to log groups prefixed with `/aws/lambda/*` to ensure the function can only write to dedicated Lambda log streams.
* **EBS Backup & Lifecycle Management:**
  * **Actions Allowed:** Grants read permissions to discover active volumes (`ec2:DescribeVolumes`) and search existing snapshots (`ec2:DescribeSnapshots`). Grants write and lifecycle permissions to generate new snapshots (`ec2:CreateSnapshot`), apply governance tags (`ec2:CreateTags`), and remove expired snapshots (`ec2:DeleteSnapshot`).
  * **Resource Scope:** Applied across EC2 resources (`*`) as EC2 describe and snapshot creation APIs require wildcard resource scoping.

### 3.2 EventBridge Invocation Permission Description (Resource-Based Policy)
The Lambda function enforces a resource-based policy to control execution triggers:

* **Principal & Action:** Explicitly permits the Amazon EventBridge service (`events.amazonaws.com`) to execute the `lambda:InvokeFunction` action against the backup Lambda function.
* **Condition & Security Scope:** Restricts invocation requests so that only execution calls originating from the specific EventBridge schedule rule (e.g., `Weekly-EBS-Backup-Rule`) within the designated AWS account and region are authorized.

---

## Section 4: AWS Lambda Function Implementation Logic

### 4.1 Configuration Requirements
* **Runtime:** Python 3.12 or Python 3.13
* **Timeout:** 3 minutes (180 seconds)
* **Memory:** 128 MB – 256 MB
* **Environment Variables:**
  * `RETENTION_DAYS`: `30` (integer representing the snapshot lifetime)

### 4.2 Functional Description of Function Logic (`lambda_function.py`)
The Python implementation carries out automated volume discovery, snapshot creation, and retention cleanup through the following step-by-step logic:

1. **Environment Initialization & Cutoff Calculation:**
   * Initializes the AWS SDK (`boto3`) EC2 client.
   * Reads the `RETENTION_DAYS` environment variable (defaulting to 30 days) and establishes constant key-value metadata tags (`CreatedBy=Lambda-Backup`).
   * Captures the current UTC time and calculates the exact retention cutoff timestamp (`now - RETENTION_DAYS`).

2. **Region-Wide Volume Discovery:**
   * Uses an EC2 paginator on the `describe_volumes` call to fetch all active EBS volume IDs across the region, preventing missing volumes in accounts with large instance counts.
   * If no volumes are returned, logs a message and exits early with a `200 OK` status.

3. **Create-First, Delete-Second Execution Strategy:**
   Iterates through each discovered EBS volume ID and executes a two-stage lifecycle process:

   * **Step A (Creation):** Calls `create_snapshot` for the current volume, appending a timestamped description and applying snapshot tags (`CreatedBy=Lambda-Backup` and `Name=Backup-{volume_id}-{timestamp}`). Stores the newly created snapshot ID.
   * **Step B (Retention Cleanup):** Queries `describe_snapshots` filtered strictly by account-owned snapshots matching the volume ID and tag `CreatedBy=Lambda-Backup`.

4. **Retention Evaluation & Safeguards:**
   * Iterates through all historical snapshots returned for the volume.
   * **Safeguard:** Skips the newly created snapshot ID to prevent premature deletion.
   * Compares the snapshot's creation time (`StartTime`) against the calculated cutoff date.
   * If `StartTime` is older than the cutoff threshold, issues a `delete_snapshot` call for that snapshot ID.

5. **Execution Summary & Output:**
   * Compiles an execution summary list containing each volume ID, its newly generated snapshot ID, and a list of purged snapshot IDs.
   * Outputs the structured summary to CloudWatch Logs for audit purposes and returns a `200 OK` HTTP status payload.

---

## Section 5: Deployment, Verification & Runbook

### 5.1 Deployment Checklist
1. Create the IAM Execution Role with the permissions described in Section 3.1.
2. Create the Lambda Function, configure the function logic described in Section 4.2, and set `RETENTION_DAYS = 30`.
3. Set Lambda function timeout to `1 minutes`.
4. Configure an EventBridge Rule or EventBridge Schedule using the target cron expression.

### 5.2 Runbook & Verification Steps
1. **Initial Execution Test (Bootstrap Phase):**
   * Manually trigger the Lambda function using a blank event `{}`.
   * Inspect CloudWatch logs to verify `ec2:DescribeVolumes` identified all target volume IDs.
   * Confirm that a snapshot was created for each volume and tagged with `CreatedBy = Lambda-Backup`.
   * Verify that no snapshots were deleted during the initial run.
2. **Retention Expiration Test:**
   * In a sandbox environment, temporarily adjust `RETENTION_DAYS` to `5` minutes.
   * Execute Lambda and verify in CloudWatch logs that older snapshots are identified and purged via `ec2:DeleteSnapshot`.
   * Confirm that the newly created snapshot remains untouched.

---

## Section 6: Simple Comparison: Built-In AWS Backups (DLM) vs. Custom Automation (Lambda)

If you are new to AWS, think of this choice like deciding between buying a ready-made automatic home appliance versus building a custom smart device yourself:

* **AWS Data Lifecycle Manager (DLM):** This is AWS's built-in, "out-of-the-box" feature. It works right away with a few clicks in the AWS Management Console, requiring zero coding.
* **AWS Lambda Custom Solution:** This is a "DIY Automation Robot." You write a small computer program (code) that runs on a schedule to do your backups. It takes more effort to set up and manage, but gives you complete control to add custom features.


| What You Need | AWS DLM (Built-In Feature) | Custom Lambda (DIY Code) |
| :--- | :--- | :--- |
| **Ease of Setup** | **Super Easy:** Set up in minutes using simple click options in the AWS console. | **Requires Coding:** You must write, test, and maintain code scripts. |
| **Maintenance** | **Zero Maintenance:** AWS handles all software updates and management behind the scenes. | **Ongoing Care:** You must periodically check and update your code and security settings. |
| **Custom Backup Rules** | **Standard Schedules:** Perfect for simple daily, weekly, or monthly backup rules. | **Ultimate Flexibility:** Create unique rules or dynamic schedules tailored to exact business needs. |
| **Pre-Backup Actions** | **Basic:** Cannot easily pause custom applications before creating a backup. | **Advanced:** Can automatically pause a database or clean temporary data right before taking a backup to ensure data isn't corrupted. |
| **Notifications & Alerts** | **Standard AWS Alerts:** Sends default notification emails through standard AWS channels. | **Custom Notifications:** Can send direct messages to Slack, Microsoft Teams, PagerDuty, or custom webhooks. |

### Plain English Recommendation
* **Choose AWS DLM if:** You want a quick, easy, and maintenance-free way to back up your servers without writing code. This is the best choice for standard AWS environments.
* **Choose Custom Lambda if:** Your application requires special treatment—such as pausing a live database right before taking a snapshot, complex custom backup schedules, or direct alerts sent to team chat rooms..