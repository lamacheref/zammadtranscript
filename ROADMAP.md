# Roadmap

## Phase 1 — Foundations (POC) ✅

- [x] Receive Zammad webhook (FastAPI endpoint)
- [x] Download audio attachment via Zammad API
- [x] Local transcription with faster-whisper (3CX formats: `.mp3`, `.wav`, `.ogg`, `.m4a`)
- [x] Update ticket title via Zammad API

## Phase 2 — Local Intelligence ✅

- [x] Title generation and client extraction via Ollama (LLM ≤ 3-4B quantized)
- [x] Create transcription article in ticket
- [x] Text cleaning (phone numbers, addresses, timestamps)

## Phase 3 — Robustness & Production (in progress)

- [x] Error handling and Zammad retries (3 attempts, backoff 10s/30s/60s)
- [x] Idempotency (anti double-transcription via state file per ticket/article)
- [x] Security: webhook secret (HMAC `X-Hub-Signature` + bearer token), environment variables
- [ ] Rate limiting on public endpoint
- [x] CPU/memory optimization for container (quantization `int8`, configurable threads)

## Phase 4 — Docker & CI/CD ✅

- [x] Multi-stage Dockerfile (builder + runtime, Python 3.12, ffmpeg, faster-whisper deps)
- [x] Docker Compose (app + Ollama, volumes, healthchecks)
- [x] GitHub Actions CI/CD (test → build/push GHCR → deploy staging)
- [x] `.dockerignore`, security hardening (non-root user)

## Phase 5 — Enhancements

- [ ] Use LLM-extracted client name to create/lookup Zammad customer
- [ ] Rate limiting on `POST /webhook/zammad`
- [ ] Structured logging (JSON) + observability (Prometheus metrics optional)
- [ ] Multi-language support (Whisper language detection)
- [ ] Unit/integration test coverage > 80%
- [ ] Dependency update automation (Dependabot/Renovate)

---

# Roadmap (English)

## Phase 1 — Foundations (POC) ✅

- [x] Receive Zammad webhook (FastAPI endpoint)
- [x] Download audio attachment via Zammad API
- [x] Local transcription with faster-whisper (3CX formats: `.mp3`, `.wav`, `.ogg`, `.m4a`)
- [x] Update ticket title via Zammad API

## Phase 2 — Local Intelligence ✅

- [x] Title generation and client extraction via Ollama (LLM ≤ 3-4B quantized)
- [x] Create transcription article in ticket
- [x] Text cleaning (phone numbers, addresses, timestamps)

## Phase 3 — Robustness & Production (in progress)

- [x] Error handling and Zammad retries (3 attempts, backoff 10s/30s/60s)
- [x] Idempotency (anti double-transcription via state file per ticket/article)
- [x] Security: webhook secret (HMAC `X-Hub-Signature` + bearer token), environment variables
- [ ] Rate limiting on public endpoint
- [x] CPU/memory optimization for container (quantization `int8`, configurable threads)

## Phase 4 — Docker & CI/CD ✅

- [x] Multi-stage Dockerfile (builder + runtime, Python 3.12, ffmpeg, faster-whisper deps)
- [x] Docker Compose (app + Ollama, volumes, healthchecks)
- [x] GitHub Actions CI/CD (test → build/push GHCR → deploy staging)
- [x] `.dockerignore`, security hardening (non-root user)

## Phase 5 — Enhancements

- [ ] Use LLM-extracted client name to create/lookup Zammad customer
- [ ] Rate limiting on `POST /webhook/zammad`
- [ ] Structured logging (JSON) + observability (Prometheus metrics optional)
- [ ] Multi-language support (Whisper language detection)
- [ ] Unit/integration test coverage > 80%
- [ ] Dependency update automation (Dependabot/Renovate)