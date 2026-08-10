# Zammad-Auto-Transcription

## Objet
Ce projet a pour objectif de créer un moteur simple de transcription recevant les webhooks zammad pour transcrire au mieux les messages réaliser par téléphone. Le fichier est un fichier "message vocal" envoyé par notre instance 3cx et reçu dans un ticket. 

Une fois la transcription effectuer, un IA simple local rédige un titre au ticket et le programme remonte les modifications :
- Titre,
- Client, 
- Texte transcrit depuis le message vocal
à notre instance Zammad.

L'ensemble doit être possible dans un petit LXC CPU only.

## Protocole

### 1. Vue d'ensemble

Flux complet :

1. 3CX dépose un message vocal dans un ticket Zammad.
2. Zammad déclenche un webhook HTTP POST vers le serveur de transcription.
3. Le serveur télécharge le fichier audio depuis le ticket.
4. Le moteur de transcription (Whisper local, CPU) transforme l'audio en texte.
5. Un LLM local rédige un titre de ticket et identifie le client.
6. Le programme met à jour le ticket Zammad via l'API REST (titre, client, texte transcrit).
7. Le serveur répond au webhook.

### 2. Composants et stack

| Composant | Rôle | Technologie |
|-----------|------|-------------|
| Serveur webhook | Réception des webhooks Zammad | Python + FastAPI/uvicorn |
| Moteur de transcription | Transcription audio local CPU | faster-whisper (modèle `base`/`small`) |
| LLM local | Titre + extraction client | Ollama (ex: `llama3.2`, `qwen2.5`) |
| Client API Zammad | Lecture / écriture des tickets | API REST Zammad + token Bearer |

### 3. Données d'entrée (webhook Zammad)

Payload JSON contenant :

- `ticket.id`, `ticket.number`, `ticket.title`
- `article.body` : chaîne vide ou texte associé
- `article.attachments` : `filename`, URL ou chemin de l'audio

Règles :

- Récupérer l'attachment audio via l'API Zammad (token Bearer).
- Accepter les formats 3CX courants : `.mp3`, `.wav`, `.ogg`, `.m4a`.

### 4. Pipeline de traitement

1. **Réception** : `POST /webhook/zammad`, validation d'un secret webhook optionnel.
2. **Téléchargement** : GET de l'attachment via l'API Zammad.
3. **Prétraitement** : conversion `ffmpeg` si besoin (mono, 16 kHz).
4. **Transcription** : faster-whisper, segmentation par phrase.
5. **Post-traitement** : nettoyage (numéros de téléphone, adresses, timestamps).
6. **Rédaction** : prompt structuré vers le LLM local → titre (≤ 80 caractères) + client si identifiable.
7. **Mise à jour Zammad** : PATCH du titre + POST d'un article de transcription + mise à jour du client.

### 5. Mise à jour Zammad (sortie)

- `PUT /api/v1/tickets/{id}` : mise à jour du `title` et du `customer_id`.
- `POST /api/v1/tickets/{id}/articles` : corps = transcription du message vocal.

### 6. Erreurs et idempotence

- Répondre `200 OK` uniquement après traitement complet ; `5xx` en cas d'échec (retry Zammad).
- Traitement en arrière-plan : répondre rapidement au webhook, exécuter la transcription, puis envoyer les mises à jour à Zammad.
- Idempotence : marquer le ticket (artefact `transcription_done` ou hash de l'article) pour éviter les doubles transcriptions en cas de renvoi du webhook.

### 7. Contraintes LXC (CPU only)

- Transcription : modèle `base`/`small` (≈ 1-2 Go RAM).
- LLM : modèle ≤ 3-4 Mds de paramètres, quantifié (Int8), ≈ 3-4 Go RAM.
- Recommandé : 8 threads CPU max, pas de GPU requis.

### 8. Sécurité

- Token API Zammad et secret webhook en variables d'environnement (jamais en clair).
- Validation de l'origine des requêtes (secret webhook).
- Rate limiting sur l'endpoint public.


