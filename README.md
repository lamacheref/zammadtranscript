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
- **Résolution client par numéro de téléphone** : extraction du pattern `De: +33...` du corps email 3CX, normalisation FR (local ↔ international, correction zéro en trop), recherche Zammad par téléphone → skip LLM si trouvé
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
.venv/bin/python -m pytest --cov=app tests/
```

### Lint

```bash
.venv/bin/ruff check app/ scripts/ tests/
.venv/bin/ruff format --check app/ scripts/ tests/
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
| `LOG_LEVEL` | Niveau de logging (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |

## Documentation

- `PROJET.md` : description du projet et protocole technique
- `TODO.md` : tâches à réaliser
- `ROADMAP.md` : feuille de route
- `CHANGELOG.md` : historique des modifications
- `documentations/` : spécifications webhook Zammad et configuration 3CX

## Versionnement

- Le fichier `VERSION` (format `M.m.f`) est mis à jour automatiquement par le CI/CD.
- Chaque modification depuis le précédent bump est un **fix** (incrémente `f`).
- Un commit `feat:` est une **minor** (incrémente `m`, remet `f` à 0).
- Le **major** (`M`) n'est jamais modifié automatiquement.

## CI/CD

Chaque forge a **son propre workflow** (Gitea ignore `.github/workflows/` dès que `.gitea/workflows/` existe, plus de double exécution) :

| Forge | Workflow |
|-------|----------|
| GitHub | `.github/workflows/ci-cd.yml` |
| Gitea | `.gitea/workflows/ci-cd.yml` |

Chaque forge pousse son image Docker dans **son propre registre** :

| Forge | Registre |
|-------|----------|
| GitHub | `ghcr.io/flamachere/zammadtranscript` |
| Gitea | `gitea.smiden.eu/flamachere/zammadtranscript` |

Pour l'authentification au push de l'image :

- **GitHub** : le `GITHUB_TOKEN` automatique suffit.
- **Gitea** : le `GITHUB_TOKEN` de Gitea Actions est refusé au push (`reqPackageAccess`) — il faut créer un secret `REGISTRY_TOKEN` contenant un **PAT Gitea** (profil → Applications → Générer un nouveau jeton, avec l'accès `write:package`). Le workflow utilise `REGISTRY_TOKEN` s'il est défini, sinon `GITHUB_TOKEN`.

Sur Gitea, le runner étant bare-metal, `actions/setup-python` échoue
(`Cannot find: node in PATH`) : le workflow utilise **UV** (`uv python install 3.12`
+ `uv venv`) à la place. Ajustez `runs-on:` au label de votre `act_runner` si
nécessaire.

En production, on peut indifféremment tirer l'image de l'un ou de l'autre registre.

## Historique des commits

### a267bd9 — fix: keep app/static directory tracked (empty dir not versioned by git)

### c5e6898 — fix: add missing jinja2 dependency for Jinja2Templates

### 516d10d — feat: add restricted centralized logging
- `app/logging_config.py`: centralized configure_logging (idempotent, noisy loggers at WARNING)
- main/worker use configure_logging instead of duplicated logging.basicConfig
- new LOG_LEVEL setting in config.py, .env.example and README
- tests for logging config
- docs: reorganize TODO into Tests/Updates/Features/v1.0.0, update ROADMAP and CHANGELOG

### f77d47a — feat: LLM client lookup/create in Zammad
- `app/zammad.py`: find_user_by_name(), create_user() methods
- `app/processor.py`: _resolve_customer() uses LLM customer_name to find/create Zammad user
- Fallback to payload customer_id if no LLM name or creation fails
- docs: TODO.md, ROADMAP.md, CHANGELOG.md updated

### 8fde04a — feat: async queue (Redis + RQ) implementation
- `app/config.py`: REDIS_URL, RQ_QUEUE_NAME settings
- `app/queue.py`: RQ queue, enqueue_transcription, process_transcription_job
- `app/main.py`: webhook enqueues job, returns 202 with job_id
- `app/worker.py`: RQ worker entry point
- docker-compose.yml: Redis service + worker service
- requirements.txt: redis, rq
- tests: updated mocks for enqueue_transcription
- docs: TODO.md, ROADMAP.md, CHANGELOG.md queue marked done

### 2e6ba06 — docs: update all docs for async queue (Redis+RQ) + manual UI
- ROADMAP.md: queue unchecked (phase 3), manual UI added (phase 5)
- TODO.md: queue + manual UI as pending tasks
- PROJET.md: async flow with queue, worker, manual UI planned, security refs updated
- README.md: async architecture, Redis config, worker deployment, manual UI feature
- All FR/EN bilingual

### 5b77f95 — docs: ROADMAP.md first block in French, second in English

### 0e82e53 — docs: update all root docs for Docker/CI/CD + English translations
- README.md: Docker deploy, config table, operation flow, FR/EN
- PROJET.md: protocol updated (202 Accepted, customer_id behavior), FR/EN
- ROADMAP.md: phases 1-4 done (Docker/CI/CD), phase 5 enhancements, FR/EN
- TODO.md: Docker/CI checked, remaining tasks (rate limiting, LLM client, lint), FR/EN
- CHANGELOG.md: Docker/CI transition entry, GPL-3.0, GitHub remote, FR/EN
- Added: Dockerfile, docker-compose.yml, .dockerignore, .github/workflows/ci-cd.yml, LICENSE (GPL-3.0)
- Removed: LXC/community-scripts references

### f8dd8ef — Prototype Zammad auto-transcription : FastAPI, faster-whisper, Ollama, Zammad API, doc et tests

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
- **Phone-based client resolution**: extracts `De: +33...` pattern from 3CX email body, normalizes French numbers (local ↔ international, fixes extra-zero bug), searches Zammad by phone → skips LLM if found
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
.venv/bin/python -m pytest --cov=app tests/
```

### Lint

```bash
.venv/bin/ruff check app/ scripts/ tests/
.venv/bin/ruff format --check app/ scripts/ tests/
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
| `LOG_LEVEL` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |

## Documentation

- `PROJET.md` : project description and technical protocol (French)
- `TODO.md` : tasks to do
- `ROADMAP.md` : roadmap
- `CHANGELOG.md` : changelog
- `documentations/` : Zammad webhook specs and 3CX configuration

## Versioning

- The `VERSION` file (`M.m.f` format) is bumped automatically by CI/CD.
- Every change since the last bump is a **fix** (increments `f`).
- A `feat:` commit is a **minor** (increments `m`, resets `f` to 0).
- The **major** (`M`) is never modified automatically.

## CI/CD

Each forge has **its own workflow** (Gitea ignores `.github/workflows/` as soon as `.gitea/workflows/` exists, no more duplicate runs):

| Forge | Workflow |
|-------|----------|
| GitHub | `.github/workflows/ci-cd.yml` |
| Gitea | `.gitea/workflows/ci-cd.yml` |

Each forge pushes its Docker image to **its own registry**:

| Forge | Registry |
|-------|----------|
| GitHub | `ghcr.io/flamachere/zammadtranscript` |
| Gitea | `gitea.smiden.eu/flamachere/zammadtranscript` |

Image push authentication:

- **GitHub**: the automatic `GITHUB_TOKEN` is enough.
- **Gitea**: Gitea Actions' `GITHUB_TOKEN` is rejected on push (`reqPackageAccess`) — create a `REGISTRY_TOKEN` secret containing a **Gitea PAT** (Profile → Applications → Generate New Token, with `write:package` scope). The workflow uses `REGISTRY_TOKEN` if defined, otherwise falls back to `GITHUB_TOKEN`.

On Gitea, the runner is bare-metal, so `actions/setup-python` fails
(`Cannot find: node in PATH`): the workflow uses **UV** (`uv python install 3.12`
+ `uv venv`) instead. Adjust `runs-on:` to your `act_runner` label if needed.

In production, the image can be pulled from either registry.

## Commit History

### a267bd9 — fix: keep app/static directory tracked (empty dir not versioned by git)

### c5e6898 — fix: add missing jinja2 dependency for Jinja2Templates

### 516d10d — feat: add restricted centralized logging
- `app/logging_config.py`: centralized configure_logging (idempotent, noisy loggers at WARNING)
- main/worker use configure_logging instead of duplicated logging.basicConfig
- new LOG_LEVEL setting in config.py, .env.example and README
- tests for logging config
- docs: reorganize TODO into Tests/Updates/Features/v1.0.0, update ROADMAP and CHANGELOG

### f77d47a — feat: LLM client lookup/create in Zammad
- `app/zammad.py`: find_user_by_name(), create_user() methods
- `app/processor.py`: _resolve_customer() uses LLM customer_name to find/create Zammad user
- Fallback to payload customer_id if no LLM name or creation fails
- docs: TODO.md, ROADMAP.md, CHANGELOG.md updated

### 8fde04a — feat: async queue (Redis + RQ) implementation
- `app/config.py`: REDIS_URL, RQ_QUEUE_NAME settings
- `app/queue.py`: RQ queue, enqueue_transcription, process_transcription_job
- `app/main.py`: webhook enqueues job, returns 202 with job_id
- `app/worker.py`: RQ worker entry point
- docker-compose.yml: Redis service + worker service
- requirements.txt: redis, rq
- tests: updated mocks for enqueue_transcription
- docs: TODO.md, ROADMAP.md, CHANGELOG.md queue marked done

### 2e6ba06 — docs: update all docs for async queue (Redis+RQ) + manual UI
- ROADMAP.md: queue unchecked (phase 3), manual UI added (phase 5)
- TODO.md: queue + manual UI as pending tasks
- PROJET.md: async flow with queue, worker, manual UI planned, security refs updated
- README.md: async architecture, Redis config, worker deployment, manual UI feature
- All FR/EN bilingual

### 5b77f95 — docs: ROADMAP.md first block in French, second in English

### 0e82e53 — docs: update all root docs for Docker/CI/CD + English translations
- README.md: Docker deploy, config table, operation flow, FR/EN
- PROJET.md: protocol updated (202 Accepted, customer_id behavior), FR/EN
- ROADMAP.md: phases 1-4 done (Docker/CI/CD), phase 5 enhancements, FR/EN
- TODO.md: Docker/CI checked, remaining tasks (rate limiting, LLM client, lint), FR/EN
- CHANGELOG.md: Docker/CI transition entry, GPL-3.0, GitHub remote, FR/EN
- Added: Dockerfile, docker-compose.yml, .dockerignore, .github/workflows/ci-cd.yml, LICENSE (GPL-3.0)
- Removed: LXC/community-scripts references

### f8dd8ef — Prototype Zammad auto-transcription : FastAPI, faster-whisper, Ollama, Zammad API, doc et tests