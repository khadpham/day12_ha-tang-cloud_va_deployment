# Lab 12 — Complete Production Agent

Kết hợp TẤT CẢ những gì đã học trong 1 project hoàn chỉnh.

## Deliverables Checklist

- [x] Dockerfile (multi-stage, < 500 MB, non-root user)
- [x] docker-compose.yml (nginx + agent + redis)
- [x] nginx.conf (load balancer configuration)
- [x] .dockerignore
- [x] Health check endpoint (`GET /health`)
- [x] Readiness endpoint (`GET /ready`)
- [x] API Key authentication (`X-API-Key` header)
- [x] Rate limiting (10 req/min per user_id)
- [x] Cost guard ($10/month per user_id, Redis-backed)
- [x] Conversation history (Redis, last 5 messages context)
- [x] Config from environment variables (12-factor)
- [x] Structured JSON logging
- [x] Graceful shutdown (SIGTERM handling)
- [x] railway.toml (Railway deployment)
- [x] render.yaml (Render deployment)
- [x] Stateless design (Redis for all state)

---

## Architecture

```
Client → Nginx (LB) → Agent × N → Redis
```

- **Nginx:** Load balancer on port 8000, routes to agent instances
- **Agent:** FastAPI app, scales with `--scale agent=3`
- **Redis:** Stores conversation history, rate limits, budgets

---

## Structure

```
06-lab-complete/
├── app/
│   ├── __init__.py
│   ├── config.py       # 12-factor settings
│   └── main.py         # Application with all features
├── utils/
│   ├── __init__.py
│   └── mock_llm.py     # Mock LLM for testing
├── nginx.conf          # Load balancer config
├── Dockerfile          # Multi-stage production build
├── docker-compose.yml  # Full stack (nginx + agent + redis)
├── railway.toml        # Railway deployment
├── render.yaml         # Render deployment
├── .env.example        # Environment template
├── .dockerignore       # Docker ignore
├── requirements.txt    # Python dependencies
└── README.md
```

---

## Local Setup

```bash
# 1. Navigate to directory
cd 06-lab-complete

# 2. Copy environment file
cp .env.example .env.local

# 3. Edit .env.local with your API key
# AGENT_API_KEY=your-secret-key-here

# 4. Start stack
docker compose up --scale agent=3

# 5. Test via nginx (port 8000)
curl http://localhost:8000/health

# 6. Test API with authentication
API_KEY=$(grep AGENT_API_KEY .env.local | cut -d= -f2)
curl -H "X-API-Key: $API_KEY" \
  -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice", "question": "What is Docker?"}'
```

---

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | No | Root info |
| GET | `/health` | No | Liveness probe |
| GET | `/ready` | No | Readiness probe (checks Redis) |
| POST | `/ask` | Yes | Ask the AI agent |

### Request/Response Examples

**POST /ask**
```bash
curl -H "X-API-Key: your-key" \
  -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user1", "question": "Hello"}'
```

**Response:**
```json
{
  "user_id": "user1",
  "question": "Hello",
  "answer": "...",
  "model": "gpt-4o-mini",
  "timestamp": "2026-04-17T...",
  "history_count": 1
}
```

---

## Deploy to Railway

```bash
# 1. Install Railway CLI
npm i -g @railway/cli

# 2. Login and init
railway login
railway init

# 3. Set variables (do this in dashboard or CLI)
railway variables set AGENT_API_KEY=your-secret-key
railway variables set REDIS_URL=your-redis-url  # or use Railway's managed Redis
railway variables set ENVIRONMENT=production

# 4. Deploy
railway up

# 5. Get public URL
railway domain
```

---

## Deploy to Render

1. Push to GitHub
2. Render Dashboard → New → Blueprint
3. Connect repo (reads `render.yaml`)
4. Set environment variables in dashboard:
   - `AGENT_API_KEY`
   - `REDIS_URL` (or use Render's managed Redis)
5. Deploy!

---

## Production Readiness Check

```bash
python check_production_ready.py
```

This validates:
- All required files exist
- No hardcoded secrets
- API endpoints defined
- Docker multi-stage build
- Rate limiting implemented
- Graceful shutdown handled

---

## Scaling

Scale agent instances (requires nginx for load balancing):
```bash
docker compose up --scale agent=5
```

Nginx automatically round-robins to all instances. Redis provides shared state so conversation history and rate limits work correctly across instances.

---

## Cost Calculation

Mock LLM cost calculation:
- Input: $0.00015 per 1K tokens
- Output: $0.0006 per 1K tokens

Default budget: $10/month per user. Tracked in Redis with key `budget:{user_id}:{YYYY-MM}`. Monthly resets automatically.