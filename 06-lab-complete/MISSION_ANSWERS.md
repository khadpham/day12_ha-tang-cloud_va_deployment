# Day 12 Lab — Mission Answers

> **Student:** _________________________
> **Student ID:** _________________________
> **Date:** _________________________

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

1. **API key hardcoded** in source code (e.g., `api_key = "sk-123..."`)
2. **Port hardcoded** (e.g., `port = 8000` instead of from env)
3. **Debug mode enabled** in production
4. **No health check endpoint** for container orchestration
5. **No graceful shutdown** handling (SIGTERM)
6. **print() logging** instead of structured JSON logs
7. **In-memory state** that doesn't persist across restarts

### Exercise 1.2: Basic version test

```bash
cd 01-localhost-vs-production/develop
pip install -r requirements.txt
python app.py

# Test:
curl http://localhost:8000/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
# Response: Works locally but not production-ready
```

### Exercise 1.3: Comparison table

| Feature | Basic | Advanced | Why Important? |
|---------|-------|----------|----------------|
| Config | Hardcoded | Environment variables | Different envs need different values; secrets shouldn't be in code |
| Health check | ❌ | ✅ `/health` | Platform knows when to restart container |
| Logging | `print()` | JSON structured | Parsable, searchable, measurable |
| Shutdown | Abrupt | Graceful (SIGTERM) | Complete requests, don't lose data |
| Secrets | Hardcoded | Env vars | Security: don't commit secrets to git |
| State | In-memory | Redis | Scale horizontally, persist across restarts |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions

1. **Base image:** `python:3.11-slim` — provides Python runtime on slim OS
2. **Working directory:** `/app` — where application code lives in container
3. **COPY requirements.txt first:** Docker cache optimization — rebuild only if requirements change
4. **CMD vs ENTRYPOINT:**
   - `CMD`: Can be overridden at runtime
   - `ENTRYPOINT`: Fixed, arguments appended

### Exercise 2.2: Build and run basic container

```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -p 8000:8000 my-agent:develop
# Image size: ~900MB+ (large because no multi-stage)
```

### Exercise 2.3: Multi-stage build comparison

```bash
cd ../production
docker build -t my-agent:advanced .
docker images | grep my-agent
# Image size: ~150-200MB (70-80% reduction)
```

**Benefits of multi-stage:**
- Smaller image size (only runtime, no build tools)
- Reduced attack surface
- Faster deployments
- Lower storage costs

### Exercise 2.4: Docker Compose architecture

```
Client → Nginx (LB) → Agent Container 1
                  → Agent Container 2
                  → Agent Container 3
                  ↓
              Redis (state)
```

Services: `nginx`, `agent` (×3), `redis`

---

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment

- **URL:** `https://my-agent.railway.app` (student's actual URL)
- **Process:**
  1. `railway login`
  2. `railway init`
  3. Set environment variables in Railway dashboard
  4. `railway up`
  5. `railway domain`

### Exercise 3.2: Render deployment

`render.yaml` is declarative — defines all services and config in YAML.
`railway.toml` is Railway-specific TOML format.

Both achieve similar goals but with different syntax.

### Exercise 3.3: Cloud Run (optional)

Uses `cloudbuild.yaml` for CI/CD pipeline and `service.yaml` for Cloud Run service definition.

---

## Part 4: API Security

### Exercise 4.1: API Key authentication

- API key checked via `X-API-Key` header
- Returns 401 if missing or invalid
- Key rotation: Change `AGENT_API_KEY` env var

### Exercise 4.2: JWT authentication

JWT flow:
1. POST `/token` with username/password
2. Server returns JWT token
3. Client sends token in `Authorization: Bearer <token>` header
4. Server verifies signature and expiry

### Exercise 4.3: Rate limiting algorithm

**Sliding Window Counter:**
- Each user has a sorted set in Redis with timestamps
- Old timestamps (> 60s) are removed
- If count >= limit, return 429
- Limit: 10 requests/minute per user

### Exercise 4.4: Cost guard implementation

```python
def check_budget(user_id: str, cost: float) -> bool:
    month_key = datetime.now().strftime("%Y-%m")
    key = f"budget:{user_id}:{month_key}"
    current = float(redis.get(key) or 0)
    if current + cost > 10.0:  # $10/month limit
        return False
    redis.incrbyfloat(key, cost)
    redis.expire(key, 35 * 24 * 3600)
    return True
```

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health checks

```python
@app.get("/health")
def health():
    return {"status": "ok"}  # Liveness probe

@app.get("/ready")
def ready():
    # Check dependencies
    redis.ping()
    return {"ready": True}  # Readiness probe
```

### Exercise 5.2: Graceful shutdown

```python
def _handle_signal(signum, _frame):
    logger.info("Shutting down gracefully...")
    # Complete current requests, close connections
    sys.exit(0)

signal.signal(signal.SIGTERM, _handle_signal)
```

### Exercise 5.3: Stateless design

**Anti-pattern (stateful):**
```python
conversation_history = {}  # In-memory — doesn't scale
```

**Correct (stateless):**
```python
history = redis.lrange(f"history:{user_id}", 0, -1)  # Redis — shared across instances
```

### Exercise 5.4: Load balancing

```bash
docker compose up --scale agent=3
# Nginx routes requests to different agent instances
# Shows X-Served-By header with instance IP
```

### Exercise 5.5: Test results

Stateless test passed — conversation persists even when killing random instance because Redis stores all state.

---

## Part 6: Final Project Summary

### What was implemented:

- ✅ Multi-stage Dockerfile (< 500 MB)
- ✅ API Key authentication
- ✅ Rate limiting (10 req/min per user)
- ✅ Cost guard ($10/month per user)
- ✅ Health + readiness endpoints
- ✅ Graceful shutdown
- ✅ Stateless design (Redis)
- ✅ Conversation history
- ✅ Structured JSON logging
- ✅ Nginx load balancer ready
- ✅ Cloud deployment config (Railway + Render)

---

## Architecture Diagram

```
┌─────────────────────────────────────────────┐
│                  Client                      │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│  Nginx (port 8000) — Load Balancer           │
│  Round-robin to agent instances              │
└──────┬──────┬──────┬────────────────────────┘
       │      │      │
       ▼      ▼      ▼
   ┌─────┐ ┌─────┐ ┌─────┐
   │Agent│ │Agent│ │Agent│  (auto-scaled)
   └──┬──┘ └──┬──┘ └──┬──┘
      │      │      │
      └──────┴──────┘
             │
             ▼
      ┌─────────────┐
      │   Redis     │
      │ (stateful)  │
      └─────────────┘
```