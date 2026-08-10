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