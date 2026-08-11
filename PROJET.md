# Zammad-Auto-Transcription

## Objet
Ce projet a pour objectif de créer un moteur simple de transcription recevant les webhooks Zammad pour transcrire au mieux les messages vocaux reçus par téléphone. Le fichier est un "message vocal" envoyé par notre instance 3CX et reçu dans un ticket.

Une fois la transcription effectuée, un LLM local rédige un titre au ticket et le programme remonte les modifications :
- Titre,
- Client (si déjà connu),
- Texte transcrit depuis le message vocal
vers notre instance Zammad.

L'ensemble doit être possible dans un conteneur Docker (CPU only).

## Protocole

### 1. Vue d'ensemble

Flux complet :

1. 3CX dépose un message vocal dans un ticket Zammad.
2. Zammad déclenche un webhook HTTP POST vers le serveur de transcription.
3. Le serveur place la demande dans une file d'attente (Redis + RQ) et répond `202 Accepted`.
4. Un worker consomme la file, télécharge le fichier audio depuis le ticket.
5. Le moteur de transcription (Whisper local, CPU) transforme l'audio en texte.
6. Un LLM local rédige un titre de ticket et identifie le nom du client.
7. Le programme met à jour le ticket Zammad via l'API REST (titre, client, texte transcrit).

Interface manuelle (prévue) : saisie d'un n° ticket → récupération audio → transcription → MAJ ticket.

### 2. Composants et stack

| Composant | Rôle | Technologie |
|-----------|------|-------------|
| Serveur webhook | Réception des webhooks Zammad | Python + FastAPI/uvicorn |
| Moteur de transcription | Transcription audio local CPU | faster-whisper (modèle `base`/`small`) |
| LLM local | Titre + extraction nom client | Ollama (ex: `llama3.2`, `qwen2.5`) |
| Client API Zammad | Lecture / écriture des tickets | API REST Zammad + token (`Token token=…`) |
| Orchestration | Conteneurisation, CI/CD, file d'attente | Docker, Docker Compose, GitHub Actions, Redis + RQ (prévu) |

### 3. Données d'entrée (webhook Zammad)

Payload JSON contenant :

- `ticket.id`, `ticket.number`, `ticket.title`
- `article.body` : chaîne vide ou texte associé
- `article.attachments` : `filename`, URL ou chemin de l'audio

Règles :

- Récupérer l'attachment audio via l'API Zammad (token Bearer).
- Accepter les formats 3CX courants : `.mp3`, `.wav`, `.ogg`, `.m4a`.

### 4. Pipeline de traitement

1. **Réception** : `POST /webhook/zammad`, validation d'un secret webhook optionnel (HMAC + bearer).
2. **Enfilement** : mise en file d'attente Redis (RQ), réponse immédiate `202 Accepted`.
3. **Traitement worker** : défilement, téléchargement attachment via API Zammad.
4. **Prétraitement** : conversion `ffmpeg` si besoin (mono, 16 kHz).
5. **Transcription** : faster-whisper, segmentation par phrase.
6. **Post-traitement** : nettoyage (numéros de téléphone, adresses, timestamps).
7. **Rédaction** : prompt structuré vers le LLM local → titre (≤ 80 caractères) + nom du client si identifiable.
8. **Mise à jour Zammad** : PUT du titre + POST d'un article de transcription + mise à jour du `customer_id` (repris du ticket si présent, le nom extrait par le LLM ne sert pas encore à créer/rechercher le client).

### 5. Mise à jour Zammad (sortie)

- `PUT /api/v1/tickets/{id}` : mise à jour du `title` et du `customer_id`.
- `POST /api/v1/tickets/{id}/articles` : corps = transcription du message vocal (type `note`).

### 6. Erreurs et idempotence

- Répondre immédiatement `202 Accepted` au webhook après enfilement, le worker traite en arrière-plan.
- En cas d'échec du pipeline worker, retries internes (3 tentatives, backoff 10s/30s/60s) ; après épuisement, l'erreur est consignée.
- Idempotence : un fichier d'état par couple ticket/article (`app/_data/state/<ticket>_<article>.json`) évite les doubles transcriptions en cas de renvoi du webhook ou ré-entrée manuelle.

### 7. Contraintes Docker (CPU only)

- Transcription : modèle `base`/`small` (≈ 1-2 Go RAM).
- LLM : modèle ≤ 3-4 Mds de paramètres, quantifié (Int8), ≈ 3-4 Go RAM.
- Recommandé : 4-8 threads CPU, pas de GPU requis.
- Image Docker multi-stage (~500 Mo), santé via `/health`.

### 8. Sécurité

- Token API Zammad et secret webhook en variables d'environnement (jamais en clair).
- Validation de l'origine des requêtes (HMAC `X-Hub-Signature` et/ou bearer token).
- Rate limiting sur l'endpoint public : à implémenter (voir `ROADMAP.md`, phase 5).

---

# Zammad-Auto-Transcription (English)

## Purpose
This project aims to create a simple transcription engine receiving Zammad webhooks to transcribe voice messages received by phone. The file is a "voicemail" sent by our 3CX instance and received in a ticket.

Once transcribed, a local LLM writes a ticket title and the program pushes updates back to Zammad:
- Title,
- Client (if already known),
- Transcribed text from the voicemail.

The whole system is designed to run in a Docker container (CPU only).

## Protocol

### 1. Overview

Full flow:

1. 3CX deposits a voicemail in a Zammad ticket.
2. Zammad triggers an HTTP POST webhook to the transcription server.
3. The server enqueues the request (Redis + RQ) and responds `202 Accepted`.
4. A worker consumes the queue, downloads the audio file from the ticket.
5. The transcription engine (local Whisper, CPU) converts audio to text.
6. A local LLM writes a ticket title and identifies the client name.
7. The program updates the Zammad ticket via REST API (title, client, transcribed text).

Manual UI (planned): enter ticket number → fetch audio → transcribe → update ticket.

### 2. Components and Stack

| Component | Role | Technology |
|-----------|------|------------|
| Webhook server | Receives Zammad webhooks | Python + FastAPI/uvicorn |
| Transcription engine | Local CPU audio transcription | faster-whisper (`base`/`small` models) |
| Local LLM | Title + client name extraction | Ollama (e.g. `llama3.2`, `qwen2.5`) |
| Zammad API client | Read/write tickets | Zammad REST API + token (`Token token=…`) |
| Orchestration | Containerization, CI/CD | Docker, Docker Compose, GitHub Actions |

### 3. Input Data (Zammad Webhook)

JSON payload containing:

- `ticket.id`, `ticket.number`, `ticket.title`
- `article.body`: empty string or associated text
- `article.attachments`: `filename`, URL or path to audio

Rules:

- Fetch audio attachment via Zammad API (Bearer token).
- Accept common 3CX formats: `.mp3`, `.wav`, `.ogg`, `.m4a`.

### 4. Processing Pipeline

1. **Reception**: `POST /webhook/zammad`, optional webhook secret validation (HMAC + bearer).
2. **Enqueue**: push to Redis queue (RQ), immediate `202 Accepted` response.
3. **Worker processing**: dequeue, download attachment via Zammad API.
4. **Preprocessing**: `ffmpeg` conversion if needed (mono, 16 kHz).
5. **Transcription**: faster-whisper, sentence segmentation.
6. **Post-processing**: cleaning (phone numbers, addresses, timestamps).
7. **Generation**: structured prompt to local LLM → title (≤ 80 chars) + client name if identifiable.
8. **Zammad Update**: PUT title + POST transcription article + `customer_id` update (taken from ticket if present; LLM-extracted name not yet used to create/lookup client).

### 5. Zammad Update (Output)

- `PUT /api/v1/tickets/{id}`: update `title` and `customer_id`.
- `POST /api/v1/tickets/{id}/articles`: body = voicemail transcription (type `note`).

### 6. Errors and Idempotency

- Respond immediately `202 Accepted` to webhook after enqueueing; worker processes in background.
- On worker pipeline failure, internal retries (3 attempts, backoff 10s/30s/60s); after exhaustion, error is logged.
- Idempotency: a state file per ticket/article pair (`app/_data/state/<ticket>_<article>.json`) prevents double transcription on webhook redelivery or manual re-entry.

### 7. Docker Constraints (CPU only)

- Transcription: `base`/`small` model (≈ 1-2 GB RAM).
- LLM: ≤ 3-4B parameter model, quantized (Int8), ≈ 3-4 GB RAM.
- Recommended: 4-8 CPU threads, no GPU required.
- Multi-stage Docker image (~500 MB), health check via `/health`.

### 8. Security

- Zammad API token and webhook secret in environment variables (never in plaintext).
- Request origin validation (HMAC `X-Hub-Signature` and/or bearer token).
- Rate limiting on public endpoint: to be implemented (see `ROADMAP.md`, phase 5).