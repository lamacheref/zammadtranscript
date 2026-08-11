# Zammad-Auto-Transcription

Moteur de transcription automatique des messages vocaux reçus dans les tickets
Zammad (appels 3CX), avec rédaction du titre et extraction du nom du client par un
LLM local (Ollama) — conçu pour fonctionner en conteneur Docker (CPU only).

Architecture asynchrone : webhook → file d'attente Redis (RQ) → worker → MAJ Zammad.

## Fonctionnalités

- Réception des webhooks Zammad (`POST /webhook/zammad`) avec enfilement immédiat
- File d'attente asynchrone (Redis + RQ) pour découpler réception et traitement
- Worker dédié : récupération audio → transcription → LLM → MAJ ticket
- Transcription locale via faster-whisper (CPU, `int8`)
- Rédaction d'un titre et extraction du nom du client via LLM local (Ollama)
- Mise à jour automatique du ticket Zammad (titre, `customer_id`, article de transcription)
- Idempotence (anti double-transcription) et retries intégrées
- Interface web manuelle (prévue) : saisie n° ticket → transcription à la demande

## Démarrage rapide (Docker)

```bash
git clone https://github.com/lamacheref/zammadtranscript.git
cd zammadtranscript
cp .env.example .env   # renseigner ZAMMAD_URL, ZAMMAD_TOKEN, WEBHOOK_SECRET, REDIS_URL
docker compose up -d
```

L'endpoint webhook est `POST /webhook/zammad` (à configurer dans Zammad comme
trigger, voir `documentations/zammad-webhook.md`). Statut de l'application :
`GET /health`.

### Déploiement manuel (Python)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# Terminal 1: API webhook
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# Terminal 2: Worker RQ
.venv/bin/python -m rq worker -u redis://localhost:6379
```

### Tests

```bash
.venv/bin/python -m pytest tests/
```

## Fonctionnement

1. Zammad envoie le webhook (payload JSON `ticket` + `article` avec attachment audio).
2. La signature HMAC (`X-Hub-Signature`) est vérifiée si `WEBHOOK_SECRET` est défini.
3. La demande est placée dans la file Redis (RQ), réponse immédiate `202 Accepted`.
4. Un worker défile : télécharge l'audio via API Zammad, normalise (ffmpeg mono 16 kHz),
   transcrit avec faster-whisper.
5. Le texte est nettoyé, un titre et le nom du client présumé sont générés par Ollama.
6. Le ticket est mis à jour (titre, `customer_id` si déjà connu du ticket) et un article de transcription est ajouté.
7. Idempotence : un état par ticket/article évite les doubles transcriptions.

## Configuration

Variables d'environnement (`.env`) :

| Variable | Description | Défaut |
|----------|-------------|--------|
| `ZAMMAD_URL` | URL de l'API Zammad | `http://localhost:8080` |
| `ZAMMAD_TOKEN` | Token API Zammad (Bearer) | — |
| `WEBHOOK_SECRET` | Secret HMAC pour validation webhook | (optionnel) |
| `REDIS_URL` | URL Redis pour file RQ | `redis://localhost:6379` |
| `WHISPER_MODEL` | Modèle faster-whisper (`base`, `small`, etc.) | `base` |
| `WHISPER_DEVICE` | Device (`cpu` ou `cuda`) | `cpu` |
| `WHISPER_COMPUTE_TYPE` | Type de calcul (`int8`, `float16`, etc.) | `int8` |
| `WHISPER_CPU_THREADS` | Threads CPU pour Whisper | `8` |
| `OLLAMA_URL` | URL du serveur Ollama | `http://localhost:11434` |
| `OLLAMA_MODEL` | Modèle LLM (ex: `llama3.2`, `qwen2.5`) | `llama3.2` |
| `HOST` / `PORT` | Bind du serveur FastAPI | `0.0.0.0:8000` |

## Documentation

- `PROJET.md` : description du projet et protocole technique
- `TODO.md` : tâches à réaliser
- `ROADMAP.md` : feuille de route
- `CHANGELOG.md` : historique des modifications
- `documentations/` : spécifications webhook Zammad et configuration 3CX

---

# Zammad-Auto-Transcription (English)

Automatic transcription engine for voice messages received in Zammad tickets
(3CX calls), with ticket title generation and client name extraction via a
local LLM (Ollama) — designed to run in a Docker container (CPU only).

Async architecture: webhook → Redis queue (RQ) → worker → Zammad update.

## Features

- Receives Zammad webhooks (`POST /webhook/zammad`) with immediate enqueueing
- Async queue (Redis + RQ) to decouple reception from processing
- Dedicated worker: fetch audio → transcribe → LLM → update ticket
- Local transcription via faster-whisper (CPU, `int8`)
- Title generation and client name extraction via local LLM (Ollama)
- Automatic Zammad ticket update (title, `customer_id`, transcription article)
- Idempotency (anti double-transcription) and built-in retries
- Manual web UI (planned): enter ticket number → transcribe on demand

## Quick Start (Docker)

```bash
git clone https://github.com/lamacheref/zammadtranscript.git
cd zammadtranscript
cp .env.example .env   # fill in ZAMMAD_URL, ZAMMAD_TOKEN, WEBHOOK_SECRET, REDIS_URL
docker compose up -d
```

The webhook endpoint is `POST /webhook/zammad` (configure in Zammad as a
trigger, see `documentations/zammad-webhook.md`). Health check: `GET /health`.

### Manual Deployment (Python)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# Terminal 1: Webhook API
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# Terminal 2: RQ Worker
.venv/bin/python -m rq worker -u redis://localhost:6379
```

### Tests

```bash
.venv/bin/python -m pytest tests/
```

## How It Works

1. Zammad sends the webhook (JSON payload `ticket` + `article` with audio attachment).
2. HMAC signature (`X-Hub-Signature`) is verified if `WEBHOOK_SECRET` is set.
3. Request is enqueued in Redis (RQ), immediate `202 Accepted` response.
4. Worker dequeues: downloads audio via Zammad API, normalizes (ffmpeg mono 16 kHz),
   transcribes with faster-whisper.
5. Text is cleaned, a title and presumed client name are generated by Ollama.
6. Ticket is updated (title, `customer_id` if already known on the ticket) and a transcription article is added.
7. Idempotency: a state file per ticket/article prevents double transcription.

## Configuration

Environment variables (`.env`):

| Variable | Description | Default |
|----------|-------------|---------|
| `ZAMMAD_URL` | Zammad API URL | `http://localhost:8080` |
| `ZAMMAD_TOKEN` | Zammad API token (Bearer) | — |
| `WEBHOOK_SECRET` | HMAC secret for webhook validation | (optional) |
| `REDIS_URL` | Redis URL for RQ queue | `redis://localhost:6379` |
| `WHISPER_MODEL` | faster-whisper model (`base`, `small`, etc.) | `base` |
| `WHISPER_DEVICE` | Device (`cpu` or `cuda`) | `cpu` |
| `WHISPER_COMPUTE_TYPE` | Compute type (`int8`, `float16`, etc.) | `int8` |
| `WHISPER_CPU_THREADS` | CPU threads for Whisper | `8` |
| `OLLAMA_URL` | Ollama server URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | LLM model (e.g. `llama3.2`, `qwen2.5`) | `llama3.2` |
| `HOST` / `PORT` | FastAPI server bind | `0.0.0.0:8000` |

## Documentation

- `PROJET.md` : project description and technical protocol (French)
- `TODO.md` : tasks to do
- `ROADMAP.md` : roadmap
- `CHANGELOG.md` : changelog
- `documentations/` : Zammad webhook specs and 3CX configuration