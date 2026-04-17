"""
Production AI Agent — Kết hợp tất cả Day 12 concepts

Checklist:
✅ Config từ environment (12-factor)
✅ Structured JSON logging
✅ API Key authentication
✅ Rate limiting (Redis, per-user)
✅ Cost guard (Redis, per-user, monthly)
✅ Input validation (Pydantic)
✅ Health check + Readiness probe
✅ Graceful shutdown
✅ Security headers
✅ CORS
✅ Error handling
✅ Conversation history (Redis)
"""
import os
import time
import signal
import logging
import json
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI, HTTPException, Security, Depends, Request, Response
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from app.config import settings
from utils.mock_llm import ask as llm_ask

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
_is_ready = False
_request_count = 0
_error_count = 0

redis_client: redis.Redis = None

def get_redis() -> redis.Redis:
    global redis_client
    if redis_client is None:
        redis_url = settings.redis_url or "redis://localhost:6379/0"
        redis_client = redis.from_url(redis_url, decode_responses=True)
    return redis_client

def get_month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")

def get_conversation_key(user_id: str) -> str:
    return f"history:{user_id}"

def get_budget_key(user_id: str) -> str:
    month = get_month_key()
    return f"budget:{user_id}:{month}"

def get_rate_key(user_id: str) -> str:
    return f"rate:{user_id}"

def get_conversation_history(user_id: str) -> list:
    r = get_redis()
    key = get_conversation_key(user_id)
    history = r.lrange(key, 0, -1)
    return [json.loads(item) for item in history] if history else []

def append_to_history(user_id: str, question: str, answer: str):
    r = get_redis()
    key = get_conversation_key(user_id)
    entry = json.dumps({
        "question": question,
        "answer": answer,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    r.rpush(key, entry)
    r.expire(key, 30 * 24 * 3600)

def check_rate_limit(user_id: str):
    r = get_redis()
    key = get_rate_key(user_id)
    now = time.time()
    window = 60

    r.zremrangebyscore(key, 0, now - window)
    count = r.zcard(key)

    if count >= settings.rate_limit_per_minute:
        retry_after = int(r.zrange(key, 0, 0, withscores=True)[0][1] + window - now) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {settings.rate_limit_per_minute} req/min",
            headers={"Retry-After": str(retry_after)},
        )

    r.zadd(key, {str(now): now})
    r.expire(key, window + 1)

def check_and_record_budget(user_id: str, input_tokens: int, output_tokens: int):
    r = get_redis()
    key = get_budget_key(user_id)
    month = get_month_key()

    current_spend = float(r.get(key) or 0)
    cost = (input_tokens / 1000) * 0.00015 + (output_tokens / 1000) * 0.0006

    if current_spend + cost > settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail=f"Monthly budget exhausted. Limit: ${settings.monthly_budget_usd}/month"
        )

    r.incrbyfloat(key, cost)
    r.expire(key, 35 * 24 * 3600)
    return current_spend + cost

def get_user_spending(user_id: str) -> float:
    r = get_redis()
    key = get_budget_key(user_id)
    return float(r.get(key) or 0)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    if not api_key or api_key != settings.agent_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Include header: X-API-Key: <key>",
        )
    return api_key

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready
    logger.info(json.dumps({
        "event": "startup",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }))

    try:
        r = get_redis()
        r.ping()
        logger.info(json.dumps({"event": "redis_connected"}))
    except Exception as e:
        logger.warning(json.dumps({"event": "redis_failed", "error": str(e)}))

    time.sleep(0.1)
    _is_ready = True
    logger.info(json.dumps({"event": "ready"}))

    yield

    _is_ready = False
    logger.info(json.dumps({"event": "shutdown"}))

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
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers.pop("server", None)
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

class AskRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=100, description="User identifier")
    question: str = Field(..., min_length=1, max_length=2000, description="Your question")

class AskResponse(BaseModel):
    user_id: str
    question: str
    answer: str
    model: str
    timestamp: str
    history_count: int

@app.get("/", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "endpoints": {
            "ask": "POST /ask (requires X-API-Key, user_id, question)",
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

    **Body:** `{"user_id": "user1", "question": "Hello"}`
    """
    check_rate_limit(body.user_id)

    history = get_conversation_history(body.user_id)
    history_context = "\n".join([f"Q: {h['question']}\nA: {h['answer']}" for h in history[-5:]])

    input_tokens = len(body.question.split()) * 2
    check_and_record_budget(body.user_id, input_tokens, 0)

    logger.info(json.dumps({
        "event": "agent_call",
        "user_id": body.user_id,
        "q_len": len(body.question),
        "history_len": len(history),
        "client": str(request.client.host) if request.client else "unknown",
    }))

    prompt = f"Conversation history:\n{history_context}\n\nCurrent question: {body.question}" if history_context else body.question
    answer = llm_ask(prompt)

    output_tokens = len(answer.split()) * 2
    check_and_record_budget(body.user_id, 0, output_tokens)

    append_to_history(body.user_id, body.question, answer)

    return AskResponse(
        user_id=body.user_id,
        question=body.question,
        answer=answer,
        model=settings.llm_model,
        timestamp=datetime.now(timezone.utc).isoformat(),
        history_count=len(history) + 1,
    )

@app.get("/health", tags=["Operations"])
def health():
    """Liveness probe. Platform restarts container if this fails."""
    return {
        "status": "ok",
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

@app.get("/ready", tags=["Operations"])
def ready():
    """Readiness probe. Load balancer stops routing here if not ready."""
    if not _is_ready:
        raise HTTPException(503, "Not ready")

    try:
        r = get_redis()
        r.ping()
    except Exception:
        raise HTTPException(503, "Redis not available")

    return {"ready": True}

@app.get("/metrics", tags=["Operations"])
def metrics(_key: str = Depends(verify_api_key)):
    """Basic metrics (protected)."""
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "error_count": _error_count,
    }

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