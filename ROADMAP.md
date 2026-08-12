# Roadmap

## Phase 1 — Fondations (POC) ✅

- [x] Réception d'un webhook Zammad (endpoint FastAPI)
- [x] Téléchargement de l'attachment audio via l'API Zammad
- [x] Transcription locale avec faster-whisper (formats 3CX : `.mp3`, `.wav`, `.ogg`, `.m4a`)
- [x] Mise à jour du titre du ticket via l'API Zammad

## Phase 2 — Intelligence locale ✅

- [x] Rédaction du titre et extraction du client via Ollama (LLM ≤ 3-4M quantifié)
- [x] Création de l'article de transcription dans le ticket
- [x] Nettoyage du texte (numéros de téléphone, adresses, timestamps)

## Phase 3 — Robustesse & production (en cours)

- [x] Gestion des erreurs et retries Zammad (3 tentatives, backoff 10s/30s/60s)
- [x] Idempotence (anti double-transcription via fichier d'état par ticket/article)
- [x] Sécurité : secret webhook (HMAC `X-Hub-Signature` + bearer token), variables d'environnement
- [x] File d'attente asynchrone (Redis + RQ) : webhook enqueue → worker traite
- [x] Optimisation CPU/mémoire pour conteneur (quantification `int8`, threads configurables)

## Phase 4 — Docker & CI/CD ✅

- [x] Dockerfile multi-stage (builder + runtime, Python 3.12, ffmpeg, deps faster-whisper)
- [x] Docker Compose (app + Ollama, volumes, healthchecks)
- [x] GitHub Actions CI/CD (test → build/push GHCR → deploy staging)
- [x] `.dockerignore`, durcissement sécurité (utilisateur non-root)

## Phase 5 — Améliorations

- [x] Utiliser le nom client extrait par le LLM pour créer/rechercher le client Zammad
- [x] Interface web manuelle : saisie n° ticket → récupération audio → transcription → MAJ ticket
- [x] **Résolution client par téléphone 3CX** : extraction `De:` depuis l'email, normalisation FR robuste (local ↔ intl, correction zéro en trop), variantes de recherche, skip LLM si trouvé
- [ ] Logging structuré (JSON) + observabilité (métriques Prometheus optionnelles)
- [ ] Support multi-langues (détection langue Whisper)
- [x] Couverture tests unitaires/intégration > 80%
- [x] Automatisation mise à jour dépendances (Renovate)

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
- [x] Async queue (Redis + RQ): webhook enqueues → worker processes
- [x] CPU/memory optimization for container (quantization `int8`, configurable threads)

## Phase 4 — Docker & CI/CD ✅

- [x] Multi-stage Dockerfile (builder + runtime, Python 3.12, ffmpeg, faster-whisper deps)
- [x] Docker Compose (app + Ollama, volumes, healthchecks)
- [x] GitHub Actions CI/CD (test → build/push GHCR → deploy staging)
- [x] `.dockerignore`, security hardening (non-root user)

## Phase 5 — Enhancements

- [x] Use LLM-extracted client name to create/lookup Zammad customer
- [x] Manual web UI: enter ticket number → fetch audio → transcribe → update ticket
- [x] **Phone-based client resolution (3CX)**: extract `De:` from email, robust FR normalization (local ↔ intl, extra-zero fix), search variants, skip LLM if found
- [ ] Structured logging (JSON) + observability (optional Prometheus metrics)
- [ ] Multi-language support (Whisper language detection)
- [x] Unit/integration test coverage > 80%
- [x] Dependency update automation (Renovate)