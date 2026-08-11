# Changelog

Toutes les modifications notables de ce projet sont documentées dans ce fichier.

## [Non publié]

### Ajouts
- Création initiale des fichiers de documentation : `PROJET.md`, `README.md`, `TODO.md`, `ROADMAP.md`
- Rédaction du protocole technique (flux webhook → transcription → LLM → mise à jour Zammad)
- Spécifications webhook Zammad (`documentations/zammad-webhook.md`)
- Spécifications envoi des messages vocaux 3CX (`documentations/3cx_envoi_message.md`)
- Prototype Python :
  - Application FastAPI + uvicorn (`app/main.py`)
  - Endpoint `POST /webhook/zammad` avec validation HMAC (`x-hub-signature`) et bearer token
  - Client API Zammad (attachments, tickets, articles) (`app/zammad.py`)
  - Transcription faster-whisper avec pré-traitement ffmpeg mono 16 kHz (`app/transcriber.py`)
  - Post-traitement du texte (nettoyage numéros/timestamps/URL) (`app/postprocess.py`)
  - Génération de titre + extraction client via Ollama (`app/title_generator.py`)
  - Pipeline orchestrateur avec idempotence et retries (`app/processor.py`)
  - Tests (pytest) : webhook, validation de signature, pipeline, idempotence, retries

### Vérification et mise à jour de la documentation
- Vérification du prototype contre le code (tests : 9/9 OK)
- `ROADMAP.md` : phases 1 et 2 cochées, phase 3 en cours (reste : rate limiting)
- `TODO.md` : ajout des tâches restantes (rate limiting, identification client via LLM, lint)
- `PROJET.md` : précisions sur la réponse `202 Accepted` + traitement en arrière-plan,
  idempotence par fichier d'état, et comportement réel du `customer_id`
- `README.md` : alignement du fonctionnement (titre/`customer_id`/article, nom client)

### Transition Docker & CI/CD
- Multi-stage `Dockerfile` (builder + runtime, Python 3.12, ffmpeg, dépendances Whisper/Ollama)
- `docker-compose.yml` (app + Ollama, volumes persistants, healthchecks, restart policy)
- GitHub Actions CI/CD (`.github/workflows/ci-cd.yml`) : test → build/push GHCR → deploy staging
- `.dockerignore` + durcissement sécurité (utilisateur non-root, cache HF local)
- Licence GPL-3.0 ajoutée
- Remote GitHub configuré : `git@github.com:lamacheref/zammadtranscript.git`
- Mise à jour docs : suppression références LXC/community-scripts, ajout sections anglaises

### Architecture asynchrone (Queue Redis + RQ)
- `app/queue.py` : file RQ, fonction job `process_transcription_job`, `enqueue_transcription`
- `app/worker.py` : point d'entrée worker RQ (`python -m app.worker`)
- `app/main.py` : webhook enqueue au lieu de `BackgroundTasks`, réponse `202` avec `job_id`
- `docker-compose.yml` : services Redis + worker, healthchecks, volumes partagés
- `requirements.txt` : `redis>=5.0`, `rq>=1.16`
- `config.py` : `redis_url`, `rq_queue_name`
- Tests mis à jour : mock `enqueue_transcription` au lieu de `processor.process`

### Client Zammad via LLM (lookup/création)
- `app/zammad.py` : `find_user_by_name()`, `create_user()` pour recherche/création utilisateur
- `app/processor.py` : `_resolve_customer()` utilise `customer_name` du LLM pour trouver/créer le client
- Fallback sur `customer_id` du payload si pas de nom LLM ou échec

---

# Changelog (English)

All notable changes to this project are documented in this file.

## [Unreleased]

### Added
- Initial documentation files: `PROJET.md`, `README.md`, `TODO.md`, `ROADMAP.md`
- Technical protocol (webhook → transcription → LLM → Zammad update flow)
- Zammad webhook specifications (`documentations/zammad-webhook.md`)
- 3CX voice message specifications (`documentations/3cx_envoi_message.md`)
- Python prototype:
  - FastAPI + uvicorn application (`app/main.py`)
  - `POST /webhook/zammad` endpoint with HMAC (`x-hub-signature`) and bearer token validation
  - Zammad API client (attachments, tickets, articles) (`app/zammad.py`)
  - faster-whisper transcription with ffmpeg mono 16 kHz preprocessing (`app/transcriber.py`)
  - Text post-processing (phone numbers, timestamps, URLs cleanup) (`app/postprocess.py`)
  - Title generation + client extraction via Ollama (`app/title_generator.py`)
  - Orchestrator pipeline with idempotency and retries (`app/processor.py`)
  - Tests (pytest): webhook, signature validation, pipeline, idempotency, retries

### Documentation Verification & Updates
- Verified prototype against code (tests: 9/9 OK)
- `ROADMAP.md`: phases 1 and 2 checked, phase 3 in progress (remaining: rate limiting)
- `TODO.md`: added remaining tasks (rate limiting, client identification via LLM, lint)
- `PROJET.md`: clarified `202 Accepted` response + background processing,
  idempotency via state file, and actual `customer_id` behavior
- `README.md`: aligned operation (title/`customer_id`/article, client name)

### Zammad Client via LLM (lookup/create)
- `app/zammad.py`: `find_user_by_name()`, `create_user()` for user lookup/creation
- `app/processor.py`: `_resolve_customer()` uses LLM `customer_name` to find/create client
- Fallback to payload `customer_id` if no LLM name or failure
- `app/queue.py`: RQ queue, `process_transcription_job` job function, `enqueue_transcription`
- `app/worker.py`: RQ worker entry point (`python -m app.worker`)
- `app/main.py`: webhook enqueues instead of `BackgroundTasks`, `202` response with `job_id`
- `docker-compose.yml`: Redis + worker services, healthchecks, shared volumes
- `requirements.txt`: `redis>=5.0`, `rq>=1.16`
- `config.py`: `redis_url`, `rq_queue_name`
- Tests updated: mock `enqueue_transcription` instead of `processor.process`
- Multi-stage `Dockerfile` (builder + runtime, Python 3.12, ffmpeg, Whisper/Ollama deps)
- `docker-compose.yml` (app + Ollama, persistent volumes, healthchecks, restart policy)
- GitHub Actions CI/CD (`.github/workflows/ci-cd.yml`): test → build/push GHCR → deploy staging
- `.dockerignore` + security hardening (non-root user, local HF cache)
- GPL-3.0 license added
- GitHub remote configured: `git@github.com:lamacheref/zammadtranscript.git`
- Docs updated: removed LXC/community-scripts references, added English sections