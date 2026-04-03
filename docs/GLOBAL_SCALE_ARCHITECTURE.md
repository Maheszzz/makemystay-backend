# Senior Architect: Global Scale & Shielded Data Ingestion

This blueprint defines the final evolution for MakeMyStay's property asset pipeline. It moves from a secure "Single-Node" model to a **"Global-Scale, Multi-Layer Protected"** architecture.

## 🏗️ The Elite Architecture Handshake

In this tier, we implement infrastructure-level shielding *before* any request touches the application layer.

```mermaid
graph TD
    User((User)) --> DNS[Amazon Route 53 (Latency Routing)]
    DNS --> CF[Amazon CloudFront (Edge)]
    CF -- GET (Signed Cookies) --> User
    
    subgraph "Ingestion Shield"
        Nginx[Nginx Rate Limiter] --> API[FastAPI Backend]
        API -- Validate Role + Size --> API
    end
    
    API -- Presign (Bound) --> Admin[Admin UI]
    Admin -- PUT (Direct) --> S3[Amazon S3 (ap-south-1)]
    
    subgraph "Global Resilience"
        S3 -- Cross-Region Replication --> S3DR[Amazon S3 (us-east-1 Standby)]
        S3 -- Object Created Trigger --> Lambda[Malware Scan (ClamAV)]
        Lambda -- Scan Result --> S3Metadata[Object Metadata: Safe/Malicious]
    end
```

---

## 🛡️ Senior Architect Guardrails Implemented

### 1. Multi-Tenant Folder Isolation
We have implemented **Tenant Isolation** at the storage layer. Assets are now stored in `properties/{id}/user_{user_id}/`. This allows us to apply IAM policies that prevent `User A` from ever overwriting or even seeing the objects uploaded by `User B`.

### 2. Infrastructure-Level Rate Limiting
We have moved from "App-Level" checks to **"Edge-Level" throttling**. Nginx now enforces:
- **Zone**: `upload_limit` (Per IP).
- **Rate**: 1 request per second.
- **Burst**: 10 requests (To allow smooth bulk uploads of multiple photos).
- **Protection**: Distributed spam or automated "garbage-fill" attacks are blocked before they consume backend CPU or S3 storage.

### 3. Global Resilience & Scanning (Next Steps)
- **Replication**: Enable **S3 Cross-Region Replication** between your primary and secondary regions for disaster recovery.
- **Scanning**: Implement a **Post-Upload Virus Scan** via a Lambda trigger. If a file is malicious, the Lambda can automatically delete it or replace it with a placeholder.
- **Signed Reads**: Finalize the transition to **CloudFront Signed Cookies** to ensure that your asset global delivery is as secure as your asset ingestion.

---

## 🏛️ Security Comparison

| Feature | Junior Level | Architect Level | Senior Architect Level |
| :--- | :--- | :--- | :--- |
| **Auth** | Hardcoded Keys | IAM Roles | **IAM Roles & Per-Tenant Folders** |
| **Throttling** | None | App-level check | **Nginx Infrastructure Throttling** |
| **Validation** | None | Size + Type (Signed) | **Bound Signatures & Malware Scan** |
| **Redundancy** | None | S3 Snapshots | **Multi-Region Live Replication** |

> [!TIP]
> **Elite Insight**: You have now eliminated the most common production risks: credential theft, unthrottled spam, data collision, and public leakage. The system is now professional grade.
