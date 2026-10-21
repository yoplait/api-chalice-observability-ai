# Production Paradigm: ECS Deployment (No Prometheus)

This document explains how to move the "closed loop" of the local lab (Prometheus + Docker Compose + Exporters) to a real AWS production environment (ECS + CloudWatch + Grafana).

**Goal:** Maintain the same observability quality and Grafana dashboards without Prometheus, using only ECS containers.
**Rule:** Local lab remains **unchanged**. This guide is for the AWS deployment only.

## 1. The Problem: "How does Grafana get data in ECS?"

In the local lab, Grafana reads from Prometheus. Prometheus "pulls" (asks) data from your containers.
In ECS, if we don't use Prometheus, the containers cannot just "wait" for a scrape. They must **push** (write) their data to a storage that Grafana can read.

**The Solution:**
1.  **The Containers (Exporters/App):** Modified to write their results directly to **CloudWatch Logs** and **CloudWatch Metrics**.
2.  **Grafana (in ECS):** Connects to CloudWatch (instead of Prometheus) and paints the graphs.

## 2. The Difference in Flow

| Feature | Local Lab (Unchanged) | AWS Deployment (The Shift) |
| :--- | :--- | :--- |
| **Data Source** | **Prometheus** (A container that scrapes everything). | **CloudWatch** (AWS Native). |
| **Exporter Role** | **Passive:** Exposes `/metrics`. Prometheus listens. | **Active:** The container *writes* the data using AWS SDK (`boto3`). |
| **Grafana Source** | Prometheus Data Source. | CloudWatch Data Source. |
| **Storage** | Prometheus TSDB. | CloudWatch Logs & Metrics. |

## 3. How to make ECS Containers "Push" to CloudWatch

In the lab, your exporter is a simple Python script. In AWS, you add a few lines so it "talks" to CloudWatch.

### Example: Local Exporter (Lab)
*Does nothing but sit there.*
```python
# Local exporter (Python)
def check_okta():
    status = http_get("okta.com")
    # Prometheus will scrape this value later.
    print(f"okta_status: {status}") 
```

### Example: AWS Exporter (ECS)
*Actively writes to CloudWatch so Grafana can read it.*
```python
# AWS Exporter (Python running on ECS)
import boto3
import requests

cloudwatch = boto3.client('cloudwatch')

def check_okta():
    status = requests.get("okta.com").status_code
    
    # WE WRITE THE DATA DIRECTLY TO CLOUDWATCH
    # Now Grafana can read it from CloudWatch!
    cloudwatch.put_metric_data(
        Namespace='MyApp/Exports',
        MetricData=[
            {
                'MetricName': 'ExternalStatus',
                'Value': 1.0 if status == 200 else 0.0,
                'Dimensions': [
                    {'Name': 'Service', 'Value': 'Okta'},
                ]
            }
        ]
    )
```

## 4. How Grafana sees it (ECS)

You don't need to change Grafana's logic, only its **Data Source**.

1.  **Grafana in ECS** connects to **CloudWatch** (not Prometheus).
2.  In Grafana, you create a "CloudWatch" panel.
3.  You select the **Namespace** (e.g., `MyApp/Exports`) and **Dimensions** (e.g., `Service=Okta`).
4.  Grafana draws the same graphs, but the data comes from CloudWatch instead of Prometheus.

## 5. Deployment Checklist (AWS Only)

To achieve this "No Prometheus" setup in your closed ECS environment:

1.  **App & Exporters (ECS):**
    *   Add a small Python dependency to your containers (`boto3` or `aws-lambda-powertools`).
    *   Add the code to `put_metric_data` (as seen above) or write structured JSON logs.
    *   Deploy as standard ECS Tasks/Services.
2.  **IAM Permissions:**
    *   Give the ECS Tasks permission to write to CloudWatch: `cloudwatch:PutMetricData`.
3.  **Grafana (ECS):**
    *   Add the `CloudWatch` plugin (usually pre-installed or easy to add).
    *   Point the Data Source to the CloudWatch region where your ECS containers live.

## 6. Summary

*   **Local:** Prometheus listens. (No code changes).
*   **AWS:** Containers talk to CloudWatch. (Small code addition).
*   **Grafana:** Always the visualizer. Just changes the cable it plugs into (Prometheus cable -> CloudWatch cable).

You get the same quality, same graphs, but the data is generated natively in CloudWatch, ready for your ECS deployment.