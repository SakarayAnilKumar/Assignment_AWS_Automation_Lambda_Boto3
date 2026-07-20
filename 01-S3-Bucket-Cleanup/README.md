# Ad-Hoc High-Throughput S3 Bucket Cleanup Architecture

This documentation details the implementation of an on-demand, manual serverless utility designed to purge expired files from an Amazon S3 bucket using pagination and bulk API actions.

---

## 1. Architecture & Manual Design Philosophy
The system utilizes a memory-efficient, streaming architecture designed to be executed manually by administrators whenever storage optimization is required.
* **Orchestration**: Triggered on-demand via the AWS Management Console.
* **Pagination Layer**: Uses the AWS `list_objects_v2` paginator client to stream data in blocks of exactly 1,000 objects per network request.
* **Execution Batching**: Matches S3's 1,000-object page size with a bulk deletion request (`delete_objects`), minimizing network overhead and API call expenses.

---

## 2. Repository Directory Structure
The operational codebase and security configurations are modularly separated within this repository. Refer to these files when deploying components:

```text
|__ screenshots/     # The screenshots captured 
├── iam_policy.json   # Minimal S3 & CloudWatch permissions
└── lambda_function.py             # Paginated batch deletion script
```

---

## 3. Prerequisites & Assumptions
Ensure the following operational dependencies are met before executing a manual purge:
* Access to an **AWS Account** with sufficient IAM permissions to create, edit, and manually execute Lambda functions.
* An active **Amazon S3 Bucket** populated with data objects requiring maintenance.
* Explicit confirmation of the target S3 bucket name (e.g., `anil-aws-assignment-boto3`) to avoid accidental data deletion.

---

## 4. Security Role Provisioning Steps
To adhere to the principle of least privilege, deploy the security parameters before building the compute layer:
1. Open the **AWS IAM Console** and navigate to **Policies** -> **Create Policy**.
2. Select the **JSON** tab and upload the contents of `iam_policy.json`.
3. Replace the placeholder bucket tokens inside the JSON file with your actual S3 target bucket name.
4. Name the policy `S3-Bulk-Cleanup-Policy`, save it, and attach it to a new IAM Role designated for **Lambda** service access.

---

## 5. System Run Profiles & Environment Settings
Create a Lambda function using the **Python 3.14** runtime framework. Upload the code found in `lambda_function.py` and apply these precise limits under the **Configuration** dashboard:
* **Memory Limits**: Standard configurations start at **128 MB**. Scale upwards to **256 MB / 512 MB** if your bucket contains over 500,000 objects to comfortably accommodate pagination loop memory tracking.
* **Execution Timeout**: Set to **5 minutes (05:00)** minimum. Large inventories require added network traversal time.
* **Execution Role**: Bind the function directly to the security profile built in **Section 4**.

---

## 6. Manual On-Demand Execution Procedures
Since this utility is not automated, it must be triggered manually using one of the following procedures:

### Test Tab in Lambda
1. Navigate to the **AWS Lambda Console** and select your cleanup function.
2. Click on the **Test** tab.
3. Keep the default empty event payload configuration (`{}`) and click the orange **Test** button.


#### Chronological Fast-Test Configuration
1. Temporarily swap out the retention logic in the code to: `datetime.timedelta(minutes=5)`.
2. Upload a simple mock item to your S3 bucket target location.
3. Wait exactly 6 minutes for the file timeline state to expire, then execute your manual test.

---

## 8. Incident Troubleshooting Matrix
Consult this guide if your manual execution sequence yields system faults or errors:

| System Error Message | Root Cause Analysis | Corrective Mitigation Steps |
| :--- | :--- | :--- |
| `Sandbox.Timedout` / `Task timed out` | The volume of S3 items on page iterations required more runtime than the Lambda timeout settings. | Access General Configuration and increase the script timeout allocation profile value up to 5 or 10 minutes. |
| `AccessDenied` / `403 Status Code` | The execution profile lacks the bulk payload authorization parameters or is missing wildcard access. | Verify `iam/lambda_execution_policy.json` contains `s3:DeleteObject` AND `s3:DeleteObjectVersion` with trailing `/*` formatting. |
| `NoSuchBucket` | The S3 client cannot locate the target name defined in your global configurations. | Check character casing and check for any typos or spaces inside the global variable string assignment area. |

---

## 9. Architectural Assessment: S3 Lifecycle Rules vs. AWS Lambda
When designing an S3 file cleanup mechanism, engineers must evaluate whether a native S3 Lifecycle Rule or a custom AWS Lambda function fits the operational goal.

### Comparison Matrix

| Feature Parameter | S3 Lifecycle Configuration | AWS Lambda Utility Script |
| :--- | :--- | :--- |
| **Operational Cost** | 100% Free architecture tier. | Subject to Lambda runtime fees & S3 `List`/`Delete` API costs. |
| **Execution Speed** | Asynchronous queue (takes up to 24–48 hours). | **Instantaneous** response upon programmatic invocation. |
| **Code Maintenance** | Zero code overhead. Native AWS configuration. | Requires language runtime updates and custom source versioning. |
| **Audit Visibility** | Coarse auditing via S3 Server Access Logs. | **Granular logging** containing exact file paths in CloudWatch. |
| **Conditional Logic** | Limited to basic creation age and folder prefixes. | **Unlimited** code logic (complex metadata or name string checks). |

### Implementation Recommendation
* **Deploy S3 Lifecycle Rules** when your only requirement is a cost-free, simple, daily "catch-all" deletion mechanism where timing delays of 24–48 hours do not impact business metrics.
* **Deploy the AWS Lambda Function** when your workflow mandates immediate manual execution, explicit dry-run confirmations, specific naming string parsing filters, or complex data compliance audit trails.
