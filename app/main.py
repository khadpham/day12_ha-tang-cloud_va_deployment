"""
Production AI Agent — Kết hợp tất cả Day 12 concepts

Checklist:
  ✅ Config từ environment (12-factor)
  ✅ Structured JSON logging
  ✅ API Key authentication
  ✅ Rate limiting
  ✅ Cost guard
  ✅ Input validation (Pydantic)
  ✅ Health check + Readiness probe
  ✅ Graceful shutdown
  ✅ Security headers
  ✅ CORS
  ✅ Error handling
"""
import os
import time
import signal
import logging
import json
from datetime import datetime, timezone
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Security, Depends, Request, Response
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from app.config import settings

# Mock LLM (thay bằng OpenAI/Anthropic khi có API key)
from utils.mock_llm import ask as llm_mock_ask

# Real LLM Clients
groq_client = None
if settings.groq_api_key:
    try:
        from groq import Groq
        groq_client = Groq(api_key=settings.groq_api_key)
        logger.info("✅ Groq client initialized")
    except ImportError:
        logger.error("❌ Groq library missing. Run pip install groq")

# ─────────────────────────────────────────────────────────
# Logging — JSON structured
# ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
_is_ready = False
_request_count = 0
_error_count = 0

# ─────────────────────────────────────────────────────────
# Redis (Stateless Store)
# ─────────────────────────────────────────────────────────
import redis
try:
    _redis = redis.from_url(settings.redis_url, decode_responses=True)
    _redis.ping()
    USE_REDIS = True
except Exception as e:
    logger.warning(f"Redis connection failed: {e}. Falling back to in-memory (NON-SCALABLE)")
    _redis = None
    USE_REDIS = False

_rate_windows_local: dict[str, deque] = defaultdict(deque)

def check_rate_limit(key: str):
    now = time.time()
    
    if USE_REDIS:
        # Redis Sliding Window using Sorted Set
        r_key = f"rate_limit:{key}"
        pipe = _redis.pipeline()
        pipe.zremrangebyscore(r_key, 0, now - 60)
        pipe.zcard(r_key)
        pipe.zadd(r_key, {str(now): now})
        pipe.expire(r_key, 60)
        _, current_count, _, _ = pipe.execute()
        
        if current_count >= settings.rate_limit_per_minute:
            raise HTTPException(429, f"Rate limit exceeded (Redis)")
    else:
        # Fallback local logic
        window = _rate_windows_local[key]
        while window and window[0] < now - 60:
            window.popleft()
        if len(window) >= settings.rate_limit_per_minute:
            raise HTTPException(429, "Rate limit exceeded (Local)")
        window.append(now)


# ─────────────────────────────────────────────────────────
# Simple Cost Guard
# ─────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────
# Redis-backed Cost Guard
# ─────────────────────────────────────────────────────────
_daily_cost_local = 0.0
_cost_reset_day_local = time.strftime("%Y-%m-%d")

def check_and_record_cost(input_tokens: int, output_tokens: int):
    global _daily_cost_local, _cost_reset_day_local
    today = time.strftime("%Y-%m-%d")
    cost = (input_tokens / 1000) * 0.00015 + (output_tokens / 1000) * 0.0006

    if USE_REDIS:
        r_key = f"cost:{today}"
        current_cost = float(_redis.get(r_key) or 0)
        if current_cost >= settings.daily_budget_usd:
            raise HTTPException(503, "Daily budget exhausted (Redis)")
        _redis.incrbyfloat(r_key, cost)
        _redis.expire(r_key, 86400 * 2) # keep for 2 days
    else:
        if today != _cost_reset_day_local:
            _daily_cost_local = 0.0
            _cost_reset_day_local = today
        if _daily_cost_local >= settings.daily_budget_usd:
            raise HTTPException(503, "Daily budget exhausted (Local)")
        _daily_cost_local += cost


# ─────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    if not api_key or api_key != settings.agent_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Include header: X-API-Key: <key>",
        )
    return api_key

# ─────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready
    logger.info(json.dumps({
        "event": "startup",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }))
    time.sleep(0.1)  # simulate init
    _is_ready = True
    logger.info(json.dumps({"event": "ready"}))

    yield

    _is_ready = False
    logger.info(json.dumps({"event": "shutdown"}))

# ─────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _request_count, _error_count
    start = time.time()
    _request_count += 1
    try:
        response: Response = await call_next(request)
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if "server" in response.headers:
            del response.headers["server"]
        duration = round((time.time() - start) * 1000, 1)
        logger.info(json.dumps({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": duration,
        }))
        return response
    except Exception as e:
        _error_count += 1
        raise

# ─────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000,
                          description="Your question for the agent")

class AskResponse(BaseModel):
    question: str
    answer: str
    model: str
    timestamp: str

# ─────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────

@app.get("/", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "endpoints": {
            "ask": "POST /ask (requires X-API-Key)",
            "health": "GET /health",
            "ready": "GET /ready",
        },
    }


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
async def ask_agent(
    body: AskRequest,
    request: Request,
    _key: str = Depends(verify_api_key),
):
    """
    Send a question to the AI agent.

    **Authentication:** Include header `X-API-Key: <your-key>`
    """
    # Rate limit per API key
    check_rate_limit(_key[:8])  # use first 8 chars as key bucket

    # Budget check
    input_tokens = len(body.question.split()) * 2
    check_and_record_cost(input_tokens, 0)

    logger.info(json.dumps({
        "event": "agent_call",
        "q_len": len(body.question),
        "client": str(request.client.host) if request.client else "unknown",
    }))

    # Call LLM
    answer = ""
    if groq_client:
        try:
            chat_completion = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": body.question}],
                model=settings.llm_model,
            )
            answer = chat_completion.choices[0].message.content
            # Update token usage from real response
            usage = chat_completion.usage
            input_tokens = usage.prompt_tokens
            output_tokens = usage.completion_tokens
        except Exception as e:
            logger.error(f"Groq API Error: {e}")
            raise HTTPException(502, f"LLM Gateway Error: {str(e)}")
    else:
        # Fallback to Mock
        answer = llm_mock_ask(body.question)
        output_tokens = len(answer.split()) * 2

    # Final cost recording
    check_and_record_cost(0, output_tokens)

    return AskResponse(
        question=body.question,
        answer=answer,
        model=settings.llm_model if groq_client else "mock-agent",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )



@app.get("/health", tags=["Operations"])
def health():
    """Liveness probe. Platform restarts container if this fails."""
    status = "ok"
    checks = {"llm": "mock" if not settings.openai_api_key else "openai"}
    return {
        "status": status,
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    """Readiness probe. Load balancer stops routing here if not ready."""
    if not _is_ready:
        raise HTTPException(503, "Not ready")
    return {"ready": True}


@app.get("/metrics", tags=["Operations"])
def metrics(_key: str = Depends(verify_api_key)):
    """Basic metrics (protected)."""
    today = time.strftime("%Y-%m-%d")
    cost = 0.0
    if USE_REDIS:
        cost = float(_redis.get(f"cost:{today}") or 0.0)
    else:
        cost = _daily_cost_local
        
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "error_count": _error_count,
        "daily_cost_usd": round(cost, 4),
        "daily_budget_usd": settings.daily_budget_usd,
        "budget_used_pct": round(cost / settings.daily_budget_usd * 100, 1),
        "storage": "redis" if USE_REDIS else "in-memory",
    }



# ─────────────────────────────────────────────────────────
# Graceful Shutdown
# ─────────────────────────────────────────────────────────
def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal", "signum": signum}))

signal.signal(signal.SIGTERM, _handle_signal)


if __name__ == "__main__":
    logger.info(f"Starting {settings.app_name} on {settings.host}:{settings.port}")
    logger.info(f"API Key: {settings.agent_api_key[:4]}****")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
