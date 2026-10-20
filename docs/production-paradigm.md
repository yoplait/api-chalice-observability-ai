# Production Paradigm: Moving from Local Lab to AWS ECS

This document explores how the "closed loop" architecture of the local lab (Prometheus + Docker Compose + Exporters) translates to a real-world, cloud-native production environment (ECS + CloudWatch + Grafana).

## 1. The Starting Point: The Local Lab (Closed Loop)

Currently, everything runs in a closed Docker loop. It works perfectly for development, but it relies on a **"Pull" model**: Prometheus is a passive database that must be awake, healthy, and constantly "scrapping" (asking) for data from the other containers.

**Current Architecture (Lab):**
```text
[Docker Network: App]
chalice-api --> exposes /metrics
blackbox-exporter --> pings chalice-api (Probe)
statuspage-exporter --> pings Okta/Twilio (Export)
[Prometheus] --> scrapes everything (Pull)
[Grafana] --> reads Prometheus (Visualization)
```

**The Problems for Production:**
- **Single Point of Failure:** If Prometheus dies, we go blind.
- **Cost of Maintenance:** Prometheus needs storage and constant tuning.
- **Network Complexity:** In AWS, containers don't always talk to each other easily without complex service meshes.

---

## 2. The Target: The Cloud-Native Environment (ECS + CloudWatch)

In AWS, we usually don't need Prometheus. CloudWatch is AWS's native "time-series database." Instead of Prometheus "pulling" data, the application "pushes" it.

**The Question:** How do we move our Exporters, Probes, and Metrics to this environment where only Grafana in ECS remains?

Here is the recommended migration path.

### Step A: The Metrics (What replaces Prometheus?)
**Recommendation: Don't deploy Prometheus on ECS.**
It is expensive to run a Prometheus server on Fargate/EC2 24/7. CloudWatch Metrics does the same job natively and handles massive volumes of data automatically.

*   **Local (Lab):** The app saves numbers in RAM (`metrics.py`). Prometheus scrapes them.
*   **Production (AWS):** The app sends numbers directly to CloudWatch using a "Sink" (we already wrote this code in `metrics_lambda.py`).
*   **Grafana's Role:** Grafana in ECS connects to CloudWatch. It sees the exact same graphs (Latency, Error Rate, Count) that it used to see in Prometheus.

### Step B: The Exporters (Statuspage, etc.)
In the lab, exporters are simple Docker containers running on the same network. In production, they should be independent services.

*   **Option 1 (Recommended): AWS Lambda.**
    Instead of a container "sitting around" doing nothing 99% of the time, turn the exporter into a Lambda function. It wakes up every 5 minutes, checks the external APIs (Okta, Twilio), and sends the results to CloudWatch. It's cheaper, scalable, and requires zero maintenance.
*   **Option 2 (Container): ECS Task.**
    You *can* deploy the exporter as an ECS Task (like we did with Grafana). This is useful if the exporter needs a complex environment or a persistent database. You would monitor it just like any other app in ECS.

### Step C: The Sondas / Blackbox Probes
In the lab, we have a `blackbox-exporter` container pinging the app's `/health` route. In AWS, we have two better tools:

1.  **Internal Probe (Does my app work?): Use AWS X-Ray.**
    X-Ray is a "trace" layer. Every time a request hits your Lambda, X-Ray records it. It gives you much more data than a simple "ping" (it tells you *which* database query was slow). It replaces the "internal blackbox".
2.  **External Probe (Can users reach my app?): Use AWS CloudWatch Synthetics.**
    This is a container that lives *outside* your VPC (in AWS's network). It pings your API Gateway every minute from different locations. If it fails, it triggers an alarm in CloudWatch just like our blackbox exporter.

---

## 3. Summary: The Paradigm Shift

| Feature | Local Lab (Current) | Production (Proposed) |
| :--- | :--- | :--- |
| **Metrics Storage** | **Prometheus** (Docker container, Pull model). | **CloudWatch Metrics** (AWS Native, Push model). No Prometheus needed. |
| **App Metrics** | Exposes `/metrics` page (Prometheus text format). | "Pushes" JSON Metrics/EMF to CloudWatch. (See `metrics_lambda.py`). |
| **Internal Monitoring** | `blackbox-exporter` container. | **AWS X-Ray** (Automatic tracing of every Lambda call). |
| **External Monitoring** | `blackbox-exporter` container (internal network). | **CloudWatch Synthetics** (Probes from AWS public internet). |
| **Third-Party Exporters** | Docker containers (e.g., Statuspage Exporter). | **AWS Lambda** (Cheap, event-driven) or ECS Task. |
| **Grafana** | Reads from Prometheus. | Reads from **CloudWatch Metrics** + **CloudWatch Logs**. |
| **Logs** | Docker logs. | **CloudWatch Logs** (JSON format, parsed by Grafana). |

## 4. What we need to do next (Roadmap)

To move from the Lab to this Production Paradigm, we would need to:

1.  **Disable the `/metrics` scrape** in production config (it's useless in Lambda anyway).
2.  **Enable `METRICS_BACKEND=cloudwatch`** so the app pushes data directly to CloudWatch.
3.  **Deploy Grafana in ECS** (we already have a Dockerfile for it) and connect it to the CloudWatch datasource.
4.  **Create a CloudWatch Dashboard** that Grafana can import, mapping our internal metrics (route, method, status) to CloudWatch dimensions.
5.  **Replace the "local" exporters** (like the statuspage one) with small Lambda functions or simple ECS tasks.

This shifts the burden from "maintaining our own Prometheus server" to "letting AWS manage the heavy lifting" — while keeping the exact same Grafana dashboards we have today.