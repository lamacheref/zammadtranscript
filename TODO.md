# TODO

Liste des tâches à réaliser pour le projet Zammad-Auto-Transcription.

## Documentation

- [x] Rédiger `PROJET.md` (objet + protocole technique)
- [x] Créer `README.md`, `CHANGELOG.md`, `ROADMAP.md`
- [x] Décrire la configuration webhook dans Zammad (événements, URL, secret)
      → `documentations/zammad-webhook.md`
- [x] Documenter la configuration 3CX (format/envoi des messages vocaux)
      → `documentations/3cx_envoi_message.md`

## Prototype

- [x] Initialiser le projet Python (FastAPI + uvicorn)
- [x] Endpoint `POST /webhook/zammad` avec validation du secret
- [x] Client API Zammad (téléchargement des attachments, lecture de ticket)
- [x] Intégration faster-whisper (modèle `base`/`small`, pré-traitement ffmpeg mono 16 kHz)
- [x] Post-traitement du texte (nettoyage numéros/adresses/timestamps)
- [x] Intégration Ollama pour le titre et l'extraction du nom du client
- [x] Mise à jour Zammad : titre, client (`customer_id`), article de transcription
- [x] Idempotence + gestion des erreurs et retries
- [x] Tests pytest (`tests/`) : pipeline, idempotence, retries, validation webhook/signature

## Docker & CI/CD

- [x] Multi-stage Dockerfile (builder + runtime, Python 3.12, ffmpeg, dépendances)
- [x] Docker Compose (app + Ollama, volumes, healthchecks, restart policy)
- [x] GitHub Actions CI/CD : test → build/push GHCR → deploy staging
- [x] `.dockerignore` + sécurité (non-root user, read-only fs où possible)

## Divers

- [ ] File d'attente asynchrone (Redis + RQ) : webhook enqueue → worker traite
- [ ] Interface web manuelle : saisie n° ticket → récupération audio → transcription → MAJ ticket
- [ ] Utiliser le nom du client extrait par le LLM pour créer/rechercher le client Zammad
      (actuellement seuls le titre et l'article sont appliqués ; `customer_id` repris du payload)
- [ ] Logging structuré (JSON) + métriques Prometheus (optionnel)
- [ ] Support multi-langues (détection langue Whisper)
- [ ] Couverture de tests > 80%
- [ ] Automatisation mise à jour dépendances (Dependabot/Renovate)
- [ ] Lint/validation du code (ruff ou équivalent)

---

# TODO (English)

Task list for the Zammad-Auto-Transcription project.

## Documentation

- [x] Write `PROJET.md` (purpose + technical protocol)
- [x] Create `README.md`, `CHANGELOG.md`, `ROADMAP.md`
- [x] Document Zammad webhook configuration (events, URL, secret)
      → `documentations/zammad-webhook.md`
- [x] Document 3CX configuration (voice message format/delivery)
      → `documentations/3cx_envoi_message.md`

## Prototype

- [x] Initialize Python project (FastAPI + uvicorn)
- [x] `POST /webhook/zammad` endpoint with secret validation
- [x] Zammad API client (attachment download, ticket reading)
- [x] faster-whisper integration (`base`/`small` model, ffmpeg mono 16 kHz preprocessing)
- [x] Text post-processing (phone numbers, addresses, timestamps cleanup)
- [x] Ollama integration for title and client name extraction
- [x] Zammad update: title, client (`customer_id`), transcription article
- [x] Idempotency + error handling and retries
- [x] Pytest tests (`tests/`): pipeline, idempotency, retries, webhook/signature validation

## Docker & CI/CD

- [x] Multi-stage Dockerfile (builder + runtime, Python 3.12, ffmpeg, dependencies)
- [x] Docker Compose (app + Ollama, volumes, healthchecks, restart policy)
- [x] GitHub Actions CI/CD: test → build/push GHCR → deploy staging
- [x] `.dockerignore` + security (non-root user, read-only fs where possible)

## Misc

- [ ] Async queue (Redis + RQ): webhook enqueues → worker processes
- [ ] Manual web UI: enter ticket number → fetch audio → transcribe → update ticket
- [ ] Use LLM-extracted client name to create/lookup Zammad customer
      (currently only title and article are applied; `customer_id` taken from payload)
- [ ] Structured logging (JSON) + Prometheus metrics (optional)
- [ ] Multi-language support (Whisper language detection)
- [ ] Test coverage > 80%
- [ ] Dependency update automation (Dependabot/Renovate)
- [ ] Code linting/validation (ruff or equivalent)