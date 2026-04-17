# DAY 12 MISSION ANSWERS: CLOUD INFRASTRUCTURE & DEPLOYMENT

**Student Name:** 2A202600253 - Phạm Đan Kha
**Deployment URL:** [https://ai-agent-cluster-szds.onrender.com/](https://ai-agent-cluster-szds.onrender.com/)
**Deployment Platform:** Render.com (Blueprint IaC)

---

## 1. Project Overview
Successful deployment of a stateless, production-ready AI agent cluster. The project transitioned from a local development script to a horizontally scalable cloud service using a modern DevOps stack.

## 2. Technical Implementation Summary

### I. Architecture & Scalability
- **Statelessness:** All stateful variables (Rate Limiting, Daily Budgets) were migrated from local memory to **Redis**. This ensures that multiple agent instances remain synchronized.
- **Scaling:** Configured a multi-node cluster architecture capable of horizontal scaling behind a global load balancer (Render).
- **Security:** Implemented `X-API-Key` authentication and standard security headers (`nosniff`, `DENY`).

### II. Infrastructure as Code (IaC)
- **Render Blueprint:** Implemented `render.yaml` at the repository root to automate the provisioning of:
  - **Web Service:** Running a high-performance Python ASGI server (Uvicorn).
  - **Managed Redis:** For persistent stateless storage.
- **Dockerization:** Developed a multi-stage `Dockerfile` based on `python:3.11-slim`, optimized for size and security (non-root user).

### III. LLM Engineering
- **Live Integration:** Connected to the **Groq API Cluster** using the `llama-3.1-8b-instant` model.
- **Usage Tracking:** Implemented token tracking for accurate cost guarding and budget enforcement.
- **Graceful Fallback:** Implemented a robust fallback system that handles missing API keys or provider downtime.

## 3. Deployment Artifacts
- **Repository Root:** [day12_ha-tang-cloud_va_deployment](https://github.com/khadpham/day12_ha-tang-cloud_va_deployment/tree/danAGY)
- **Dockerfile:** [Root Dockerfile](./Dockerfile)
- **Blueprint:** [Root render.yaml](./render.yaml)

## 4. Final Validation Results
- **Status Endpoint:** `GET /health` -> **200 OK**
- **Metrics Endpoint:** `GET /metrics` -> **Authorized**
- **AI Logic:** `POST /ask` -> **Functional (API Verified)**

---
**Status: MISSION ACCOMPLISHED**
The system is now fully autonomous and accessible globally.
