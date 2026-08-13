# Changelog

Toutes les modifications notables de ce projet sont documentées dans ce fichier.

## [Non publié]

### Ajouts
- **En-tête qualité** : ajout systématique de « Transcription par ZammadTranscript - Attention à la qualité »
sur tous les articles de transcription (flux manuel et automatique).

### Corrections
- API Zammad : création d'article sur le bon endpoint `POST /api/v1/ticket_articles`
  (`ticket_id` dans le corps) — l'ancien `POST /api/v1/tickets/{id}/articles`
  retournait 404 "This page doesn't exist.". `get_article` corrigé de même
  (`GET /api/v1/ticket_articles/{id}`).
- Registre Gitea (CI) : retrait de `https://` de l'URL du registre utilisé dans
  les tags Docker (ancre `sed ^` ne matchait jamais avec le préfixe `registry=`).
- Pull du modèle Ollama : utilisation de `OLLAMA_URL` configuré au lieu de
  `127.0.0.1:11434` personnelle du client (`Connection refused` en conteneur).
- Pytest Gitea : `pythonpath = "."` (syntaxe sans crochets) rend `app`/`scripts`
  importables sous `uv run pytest`.

### Ajouts
- CI/CD : scission en deux workflows indépendants :
  - `.github/workflows/ci-cd.yml` (GitHub) : `actions/setup-python`, image poussée sur `ghcr.io`.
  - `.gitea/workflows/ci-cd.yml` (Gitea) : utilise **UV** au lieu de `actions/setup-python`
    (échec `Cannot find: node in PATH` sur le runner bare-metal Debian 13),
    image poussée sur le registre de l'instance Gitea.
  - Gitea ignore `.github/workflows/` dès que `.gitea/workflows/` existe → pas de double exécution.
- Téléchargement automatique du modèle Ollama au premier lancement :
  - `app/model_download.py` : pull du modèle avec progression partagée via Redis
    (verrou dédupliqué entre l'API et le worker).
  - Déclenché au démarrage de l'API (lifespan) et du worker.
  - Filet de sécurité dans `TitleGenerator.generate` (télécharge si absent).
  - UI : le modèle manquant devient un bouton « Télécharger » qui se transforme
    en barre de progression pendant le pull (endpoints `POST /ui/models/download`).
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

### Logging restreint
- `app/logging_config.py` : configuration centralisée du logging (format unique, idempotente)
- Loggers bruyants (httpx, faster-whisper, etc.) réduits à `WARNING` par défaut
- `app/main.py` / `app/worker.py` : utilisent `configure_logging()` au lieu de `logging.basicConfig` dupliqué
- `config.py` + `.env.example` : nouveau réglage `LOG_LEVEL` (défaut `INFO`)

### Correction
- `requirements.txt` : ajout de `jinja2` (requis par `Jinja2Templates`, manquait en CI/Docker)

### Versionnement automatique
- `VERSION` : fichier global au format `M.m.f`
- `scripts/bump_version.py` : calcule le prochain numéro de version (fix = `f`, `feat:` = minor, major jamais automatique)
- CI/CD : job `version` (commit + tag `vX.Y.Z`), image Docker taguée avec la version
- Tests : `tests/test_bump_version.py`

### Tests & qualité
- Couverture de tests portée à 97 % (bug corrigé : `TemplateResponse(request, name, context)`)
- `pyproject.toml` : configuration ruff (`E`, `F`, `W`, `I`, `UP`, `B`)
- Lint + formatage ruff appliqués sur `app/`, `scripts/`, `tests/`
- CI/CD : étape lint (`ruff check` + `format --check`) et tests avec couverture (`--cov-fail-under=80`)
- `requirements.txt` : ajout de `ruff`, `pytest-cov`

### Automatisation mises à jour de dépendances
- `renovate.json` : configuration Renovate (pip, Docker/compose, GitHub Actions)
- Planification hebdomadaire, regroupement `minor`/`patch` par manager, dashboard et alertes sécurité
- `documentations/renovate.md` : installation GitHub (app hébergée) et Gitea (self-hosted)

### Résolution client par téléphone (optimisation 3CX)
- `app/processor.py` : `_extract_phone_from_3cx_email()` extrait le pattern `De: +33...` du corps HTML 3CX
- `_normalize_french_phone()` : normalisation robuste FR (local 0XXXXXXXXX ↔ international +33XXXXXXXXX, correction bug zéro en trop `+3302...` → `+332...`, nettoyage espaces/tirets/points)
- `_phone_variants()` : génère toutes les variantes (E.164, local 0X XX XX XX XX, compact 33..., espaces) pour matcher quel que soit le format stocké dans Zammad
- `app/zammad.py` : `find_user_by_phone()` recherche via `/api/v1/users/search?query=` sur champs `phone`, `mobile`, `fax`
- `app/processor.py` : `_resolve_customer()` tente d'abord la recherche par téléphone (toutes variantes) → si trouvé, **skip LLM** pour le nom client → fallback LLM + création si échec
- Indicateurs FR supportés : métropole (1-5, 6, 7, 9) + DOM/TOM (590, 594, 596, 262, 269, 681, 689)

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

### Restricted logging
- `app/logging_config.py`: centralized logging configuration (single format, idempotent)
- Noisy loggers (httpx, faster-whisper, etc.) reduced to `WARNING` by default
- `app/main.py` / `app/worker.py`: use `configure_logging()` instead of duplicated `logging.basicConfig`
- `config.py` + `.env.example`: new `LOG_LEVEL` setting (default `INFO`)

### Fix
- `requirements.txt`: added `jinja2` (required by `Jinja2Templates`, missing in CI/Docker)

### Automatic versioning
- `VERSION`: global file in `M.m.f` format
- `scripts/bump_version.py`: computes the next version number (fix = `f`, `feat:` = minor, major never automatic)
- CI/CD: `version` job (commit + tag `vX.Y.Z`), Docker image tagged with the version
- Tests: `tests/test_bump_version.py`

### Tests & quality
- Test coverage raised to 97% (bug fix: `TemplateResponse(request, name, context)`)
- `pyproject.toml`: ruff configuration (`E`, `F`, `W`, `I`, `UP`, `B`)
- ruff lint + format applied on `app/`, `scripts/`, `tests/`
- CI/CD: lint step (`ruff check` + `format --check`) and tests with coverage (`--cov-fail-under=80`)
- `requirements.txt`: added `ruff`, `pytest-cov`
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

### Phone-based Client Resolution (3CX Optimization)
- `app/processor.py`: `_extract_phone_from_3cx_email()` extracts `De: +33...` pattern from 3CX email HTML body
- `_normalize_french_phone()`: robust FR normalization (local 0XXXXXXXXX ↔ international +33XXXXXXXXX, fixes extra-zero bug `+3302...` → `+332...`, strips spaces/dashes/dots)
- `_phone_variants()`: generates all plausible variants (E.164, local 0X XX XX XX XX, compact 33..., spaced) to match whatever format is stored in Zammad
- `app/zammad.py`: `find_user_by_phone()` searches via `/api/v1/users/search?query=` on `phone`, `mobile`, `fax` fields
- `app/processor.py`: `_resolve_customer()` attempts phone lookup first (all variants) → if found, **skips LLM** for client name → fallback to LLM + creation on failure
- Supported FR prefixes: metro (1-5, 6, 7, 9) + overseas (590, 594, 596, 262, 269, 681, 689)