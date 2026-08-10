# Zammad-Auto-Transcription

Moteur de transcription automatique des messages vocaux reçus dans les tickets
Zammad (appels 3CX), avec rédaction du titre et identification du client par un
LLM local — conçu pour fonctionner sur un petit LXC CPU only.

## Fonctionnalités

- Réception des webhooks Zammad (`POST /webhook/zammad`)
- Récupération de l'attachment audio depuis le ticket
- Transcription locale via faster-whisper (CPU)
- Rédaction d'un titre et extraction du client via un LLM local (Ollama)
- Mise à jour automatique du ticket Zammad (titre, client, texte transcrit)

## Démarrage rapide

### Prérequis

- Python ≥ 3.12
- `ffmpeg` disponible dans le PATH
- Une instance Zammad (API + token)
- Ollama avec un modèle local (ex. `llama3.2`)

### Installation et lancement

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # puis renseigner ZAMMAD_URL / ZAMMAD_TOKEN / WEBHOOK_SECRET
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

L'endpoint webhook est `POST /webhook/zammad` (à configurer dans Zammad comme
trigger, voir `documentations/zammad-webhook.md`). Statut de l'application :
`GET /health`.

### Tests

```bash
.venv/bin/python -m pytest tests/
```

## Fonctionnement

1. Zammad envoie le webhook (payload JSON `ticket` + `article` avec attachment audio).
2. La signature HMAC (`X-Hub-Signature`) est vérifiée si `WEBHOOK_SECRET` est défini.
3. L'audio est téléchargé via l'API Zammad, normalisé (ffmpeg mono 16 kHz) puis
   transcrit avec faster-whisper.
4. Le texte est nettoyé, un titre et le nom du client sont générés par Ollama.
5. Le ticket est mis à jour (titre, `customer_id`) et un article de transcription est ajouté.
6. Idempotence : un état par ticket/article évite les doubles transcriptions.

## Documentation

- `PROJET.md` : description du projet et protocole technique
- `TODO.md` : tâches à réaliser
- `ROADMAP.md` : feuille de route
- `CHANGELOG.md` : historique des modifications
- `documentations/` : spécifications webhook Zammad et configuration 3CX