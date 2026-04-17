# Deployment Information — Day 12 Lab

> **Student:** _________________________
> **Student ID:** _________________________
> **Date:** _________________________

---

## Public URL

```markdown
https://your-agent.railway.app
```

---

## Platform

- [ ] Railway
- [ ] Render
- [ ] Cloud Run
- [ ] Other: _______________

---

## Environment Variables Set

| Variable | Value | Notes |
|----------|-------|-------|
| `ENVIRONMENT` | production | |
| `AGENT_API_KEY` | `<secret>` | Changed from default |
| `REDIS_URL` | `<platform Redis>` | Platform-managed or external |
| `MONTHLY_BUDGET_USD` | 10.0 | Per user |
| `RATE_LIMIT_PER_MINUTE` | 10 | |

---

## Test Commands

### Health Check
```bash
curl https://your-agent.railway.app/health
# Expected: {"status": "ok", "version": "1.0.0", ...}
```

### Readiness Check
```bash
curl https://your-agent.railway.app/ready
# Expected: {"ready": true}
```

### API Test (without authentication)
```bash
curl https://your-agent.railway.app/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
# Expected: 401 Unauthorized
```

### API Test (with authentication)
```bash
curl -H "X-API-Key: YOUR_API_KEY" \
  https://your-agent.railway.app/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "What is Docker?"}'
# Expected: 200 OK with response
```

### Rate Limiting Test
```bash
for i in {1..15}; do
  curl -H "X-API-Key: YOUR_API_KEY" \
    https://your-agent.railway.app/ask -X POST \
    -H "Content-Type: application/json" \
    -d "{\"user_id\": \"test\", \"question\": \"test $i\"}"
done
# Expected: Eventually returns 429
```

### Conversation History Test
```bash
# First message
curl -H "X-API-Key: YOUR_API_KEY" \
  https://your-agent.railway.app/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice", "question": "My name is Alice"}'

# Second message (should remember context)
curl -H "X-API-Key: YOUR_API_KEY" \
  https://your-agent.railway.app/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice", "question": "What is my name?"}'
```

---

## Screenshots

Include screenshots of:
- [ ] Deployment dashboard showing running service
- [ ] Health check returning 200
- [ ] API test with valid API key
- [ ] Rate limiting in action (429 response)
- [ ] Repository structure

---

## Notes

_Write any deployment notes, issues encountered, or additional configuration._