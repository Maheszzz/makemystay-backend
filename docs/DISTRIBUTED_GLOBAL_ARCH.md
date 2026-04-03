# Distributed Systems Architecture: Global Failover & Redundancy

This blueprint defines the final "Systems Master" posture for MakeMyStay's global infrastructure. We have moved from a geographic mesh to a **Self-Healing Global Distribution**.

## 🌐 The Master Global Topology

In this tier, we implement **Infrastructure Failover** at the edge, ensuring zero downtime even during total regional outages.

```mermaid
graph TD
    User((Global User)) --> R53[Route 53: Latency Routing]
    R53 --> CF[CloudFront Edge]
    
    subgraph "Edge Logic (Systems Master)"
        CF -- GET (OAC Protected) --> OG[CloudFront Origin Group]
        OG -- Primary --> S3IN[S3: Mumbai]
        OG -- Failover --> S3US[S3: Virginia]
    end
    
    subgraph "Ingestion Shield"
        Nginx[Nginx Rate Limiter] --> API[FastAPI Backend]
        API -- Validate Role + Size --> API
    end
    
    API -- Presign (Bound) --> Admin[Admin UI]
    Admin -- PUT (Regional) --> S3Regional[Regional S3]
    
    S3Regional -- Star Replication --> S3IN
    S3IN -- Star Replication --> S3US
    S3IN -- Star Replication --> S3EU

    Note over CF, OG: CloudFront Origin Group Failover
    Note over Admin, S3Regional: Region-Aware Write Fallback
```

---

## 🛡️ Systems Master Guardrails Implemented

### 1. Instant Visibility (Cache-Busting)
To eliminate the window of "Upload-Success-but-Image-Missing" caused by replication lag, the backend now appends a `?v=<timestamp>` versioning string to the returned public URL. This bypasses edge caching for the immediate view, providing **Real-time Observed Consistency** for the user.

### 2. CloudFront Origin Groups (DR)
We have configured a **CloudFront Origin Group**. CloudFront treats Mumbai as the primary data source. If Mumbai returns a `5xx` error or times out, CloudFront automatically and transparently reroutes the request to the Virginia standby bucket. This ensures **Read Availability** even during a primary region disaster.

### 3. Failover Observability
The backend now emits a specialized log marker: `[FAILOVER_ACTIVE]`. 
- **Action**: You should create a **CloudWatch Metric Filter** on this string.
- **Outcome**: You can trigger a PagerDuty or SNS alarm the moment your system starts falling back to the primary region due to a regional ingestion failure.

### 4. Advanced Edge Security (OAC)
We recommend transitioning from custom header secrets to **Amazon S3 Origin Access Control (OAC)**. OAC uses AWS SigV4 to sign requests at the edge, ensuring that S3 only accepts requests that are cryptographically verified by CloudFront, eliminating the risk of header spoofing.

---

## 🏛️ Final Strategic Maturity

| Posture | Level | Capability |
| :--- | :--- | :--- |
| **Regional Success** | Staff | Basic HA |
| **Zero-Trust Security** | Architect | No Secrets |
| **Shielded Ingestion** | Senior Architect | Spam Protected |
| **Global Multi-Region** | Distributed Architect | Low Latency |
| **Self-Healing Mesh** | **Systems Master** | **Observed Consistency & Read Failover** |

> [!TIP]
> **Elite Insight**: This represents the pinnacle of AWS infrastructure design. Your system is now optimized for the three pillars of global systems: **Latency**, **Consistency**, and **Availability**.
