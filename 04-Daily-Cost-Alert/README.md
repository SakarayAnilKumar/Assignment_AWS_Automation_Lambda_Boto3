# AWS Automated Cost Optimization & Threshold Alerting System
---

## Section 1: Architecture Blueprint & Solution Overview

### Executive Summary
Managing cloud expenditure effectively requires continuous visibility and proactive controls. While traditional CloudWatch `Billing` metrics provided baseline spend monitoring, that legacy mechanism was limited to `us-east-1` and lacked granular operational metrics. 

This guide details an enterprise-grade automated cost monitoring pipeline using the modern **AWS Cost Explorer API (`ce:GetCostAndUsage`)**, **AWS Lambda**, **Amazon SNS**, and **Amazon EventBridge**. This solution delivers precise, real-time Month-To-Date (MTD) billing insight and sends proactive notifications whenever unblended cloud costs cross defined thresholds.

### Architectural Blueprint

```text
 ┌────────────────────────┐
 │   Amazon EventBridge   │  (Daily Cron Schedule: cron(40 22 * * ? *))
 │    (Scheduled Rule)    │
 └───────────┬────────────┘
             │ Invokes
             ▼
 ┌────────────────────────┐        Queries Spend MTD
 │       AWS Lambda       ├─────────────────────────────────┐
 │ (Python 3.12 Runtime)  │                                 │
 └───────────┬────────────┘                                 ▼
             │ Exceeds Threshold?                 ┌───────────────────┐
             ├─────────────────┐                  │ AWS Cost Explorer │
             │ Yes             │ No               │      (API)        │
             ▼                 ▼                  └───────────────────┘
 ┌──────────────────────┐  ┌──────────────────┐
 │      Amazon SNS      │  │ Log to CloudWatch│
 │   (Alert Topic)      │  │ (No Alert Sent)  │
 └───────────┬──────────┘  └──────────────────┘
             │ Publishes
             ▼
 ┌──────────────────────┐
 │   Subscriber Email   │
 │   / Chat Webhooks    │
 └──────────────────────┘
```

### Key Workflow Steps
1. **EventBridge Scheduler:** Triggers the pipeline daily at a specified time (e.g., 08:00 UTC).
2. **Lambda Handler Execution:** Calculates the exact Month-to-Date time window and queries the AWS Cost Explorer API.
3. **Cost Evaluation:** Compares MTD Unblended Costs against the configured environment variable threshold.
4. **Notification Dispatch:** If spend $\ge$ threshold, formats a structured alert and publishes to the SNS Topic.
5. **Observability:** Logs all operational metrics, dates, and spend values to AWS CloudWatch Logs.

### Financial Footprint Analysis
* **Cost Explorer API Calls:** $0.01 per request. Scheduled once daily $\approx$ **$0.30/month**.
* **AWS Lambda:** Well within AWS Free Tier limits (1 Million requests/month).
* **Amazon SNS:** Free for the first 1,000 email deliveries/month.

---

## Section 2: Identity & Access Management (IAM) Configuration

Adhering to the **AWS Least Privilege Principle**, the Lambda execution role must be explicitly bounded to only read cost data and publish to the specific SNS topic created for this pipeline.

### IAM Execution Role Specification

* **Role Name:** `AWSLambdaCostNotifierRole`
* **Managed Policy Attachment:** `AWSLambdaBasicExecutionRole` (Provides `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents`).
* **Custom Inline Policy Name:** `CostNotifierPermissions`

> **Note:** The `ce:GetCostAndUsage` action does not support resource-level permissions and must target `*`. However, `sns:Publish` MUST be constrained to the specific SNS Topic ARN.

---

## Section 3: Amazon SNS Notification Infrastructure

### Provisioning the Topic

1. Navigate to **Amazon SNS** > **Topics** > **Create Topic**.
2. Select **Standard** topic type.
3. Set **Name** to `aws-cost-alerts-topic`.
4. Set **Display Name** to `AWS Cost Alert`.
5. Keep default Server-Side Encryption (SSE) settings or enable AWS KMS with an AWS Managed Key (`aws/sns`).
6. Click **Create Topic**.

### Subscribing Endpoints

1. Within the `aws-cost-alerts-topic` console page, select **Create subscription**.
2. **Protocol:** Select `Email`.
3. **Endpoint:** Enter the target administrator or group distribution email address (e.g., `cloud-ops@company.com`).
4. Click **Create subscription**.
5. **Critical Verification:** Open the endpoint email inbox and click **Confirm Subscription** inside the AWS verification email. Ensure the status transitions from `Pending Confirmation` to `Confirmed`.

---

## Section 4: AWS Lambda Function Implementation

### Function Specifications
* **Runtime:** Python 3.12
* **Handler:** `lambda_function.lambda_handler`
* **Architecture:** x86_64 or arm64 (Graviton)
* **Timeout:** 15 seconds
* **Memory:** 128 MB

### Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `SNS_TOPIC_ARN` | **Yes** | *None* | Full ARN of the target SNS topic. |
| `COST_THRESHOLD` | **Yes** | `50.00` | MTD limit in USD before triggering an alert. |

---

## Section 5: Amazon EventBridge Automation & Scheduling

### Rule Creation & Cron Syntax

To automate daily spending checks, configure an EventBridge Schedule/Rule:

* **Rule Name:** `daily-aws-cost-check-rule`
* **Schedule Pattern:** `cron(40 22 * * ? *)` *(Executes daily at 22:40 IST)*
* **Target:** AWS Lambda Function (`AWS-Cost-Threshold-Alert`)

---

## Section 6: Operational Testing & Verification Procedures

To validate the end-to-end alert pipeline without waiting for actual high spend, perform the following verification workflow:

### Test Execution Matrix

| Test Case ID | Test Objective | Procedure | Expected Result |
| :--- | :--- | :--- | :--- |
| **TC-01** | Below-Threshold Execution | Set `COST_THRESHOLD` = `10000.00`. Trigger Lambda manually with `{}`. | Execution succeeds (200). Logs show spend < threshold. No SNS email sent. |
| **TC-02** | Forced Threshold Breach | Set `COST_THRESHOLD` = `0.00`. Trigger Lambda manually with `{}`. | Execution succeeds (200). SNS notification published. Alert email received. |


> **Post-Test Action:** Ensure `COST_THRESHOLD` is restored to your actual operational threshold (e.g., `$50.00`) after testing!

---

## Section 7: Enterprise Comparison: Custom Lambda vs. AWS Budgets

When evaluating cloud governance controls, team leaders often compare custom Lambda alerting with native AWS Budgets. Both approaches have distinct architectural advantages:

| Dimension | Managed AWS Budgets | Custom Lambda + Cost Explorer API |
| :--- | :--- | :--- |
| **Deployment Complexity** | Low (Console UI, CloudFormation, or Terraform) | Medium (Requires Lambda code, IAM role, EventBridge) |
| **Pricing Structure** | First 2 budgets free; $0.02/day per budget thereafter | Cost Explorer API ($0.01/call) $\approx$ $0.30/month total |
| **Notification Routing** | Email, SNS, AWS Chatbot | Unlimited (Slack Webhooks, MS Teams, PagerDuty, Jira, Opsgenie) |
| **Logic Customization** | Static limit or Auto-adjusting percentage | Complex logic (Service breakdowns, day-over-day velocity, anomaly logic) |
| **Automated Remediation** | Built-in action policies (IAM/SCP attach, EC2 stop) | Fully customizable (Shut down non-prod RDS, drop auto-scaling, revoke permissions) |

### Architectural Recommendation
* Standard account-level alerts $\rightarrow$ **Use AWS Budgets**.
* Multi-channel rich notifications (Slack/Teams blocks) or custom dynamic math (e.g., alerting when daily spend rate jumps by >30%) $\rightarrow$ **Use Custom Lambda**.
