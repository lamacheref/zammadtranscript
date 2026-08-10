# Spécifications — Webhook Zammad

Rédaction de la tâche « Décrire la configuration webhook dans Zammad (événements, URL, secret) »
du `TODO.md`. Ce document spécifie la configuration webhook côté Zammad et les
données reçues par notre moteur de transcription.

## 1. Principe

Zammad envoie un webhook HTTP POST vers notre serveur (`/webhook/zammad`) lorsqu'un
ticket/article est créé (message vocal 3CX reçu dans un ticket). Le webhook est
déclenché via un **trigger** (ou scheduler) qui sélectionne le webhook à utiliser.

## 2. Configuration côté Zammad

### 2.1 Navigation

- Menu Administration (`Admin`) → **Channels** → **Webhooks** → bouton **New Webhook**.

### 2.2 Champs du webhook

| Champ | Valeur recommandée pour ce projet |
|-------|-----------------------------------|
| Name | `zammad-auto-transcription` |
| Endpoint | `https://<hôte-transcription>/webhook/zammad` |
| Request method | `POST` |
| SSL verification | `yes` (si certificat valide) |
| Authentication | `Bearer Token` — voir § 2.3 |
| HMAC SHA1 Signature Token | renseigner le secret — voir § 2.4 |
| Custom Payload | `off` (utiliser le payload par défaut) |

> Zammad ignore les paramètres d'authentification basique passés dans l'URL de l'endpoint ;
> l'authentification se configure via les champs dédiés.

### 2.3 Authentification (Bearer Token)

Le serveur de transcription peut exiger un bearer token. Configuration :

1. **Authentication** = `Bearer Token`.
2. Renseigner le token attendu par le serveur.
3. Zammad l'enverra dans le header `Authorization: Bearer <token>`.

### 2.4 Signature (secret)

- Zammad accepte un **HMAC SHA1 Signature Token** (ligne de l'époque : le champ s'appelle
  encore HMAC) : si renseigné, **toutes** les requêtes webhook contiennent le header
  `x-hub-signature`.
- Ce secret ne chiffre **pas** le payload : il fournit une signature HMAC du corps de la
  requête permettant de vérifier l'origine. **Ne pas diffuser le secret en clair.**
- Le serveur doit comparer la signature à l'aide d'une comparaison à temps constant
  (`hmac.compare_digest` en Python).

## 3. En-têtes de requête (headers)

Zammad envoie systématiquement :

| Header | Contenu |
|--------|---------|
| `User-Agent` | `"Zammad User Agent"` |
| `X-Zammad-Trigger` | nom du trigger qui a déclenché l'envoi |
| `X-Zammad-Delivery` | identifiant unique aléatoire de l'envoi |
| `X-Hub-Signature` | hash SHA-1 de la signature HMAC-SHA1 (si secret configuré) |
| `Authorization` | `Bearer <token>` (si authentication = Bearer Token) |

## 4. Payload par défaut (JSON)

Si `Custom Payload` est désactivé, Zammad envoie le payload par défaut. Il contient
l'objet `ticket` complet (impossible d'omettre les « vides » : les webhooks reçus
incluent tous les champs, `null` compris) et l'objet `article` (article créateur).

### 4.1 Structure

```json
{
  "ticket": {
    "id": 81,
    "number": "10081",
    "title": "Webhook-Test",
    "state": "open",
    "state_id": 2,
    "customer_id": 8,
    "customer": { "id": 8, "firstname": "Emily", "lastname": "Adams", "email": "emily@example.com", "organization": "Awesome Customer Inc.", "...": "..." },
    "owner": { "id": 5, "firstname": "Emma", "lastname": "Taylor", "...": "..." },
    "group": { "id": 3, "name": "Service Desk", "...": "..." },
    "organization": { "id": 3, "name": "Awesome Customer Inc.", "...": "..." },
    "priority": { "id": 2, "name": "2 normal", "...": "..." },
    "created_at": "2020-11-13T14:34:35.282Z",
    "updated_at": "2020-11-13T14:34:35.333Z",
    "...": "autres champs ticket (custom objects éventuels inclus)"
  },
  "article": {
    "id": 104,
    "ticket_id": 81,
    "type": "phone",
    "type_id": 5,
    "sender": "Customer",
    "sender_id": 2,
    "from": "Emily Adams <emily@example.com>",
    "to": "Service Desk",
    "body": "<texte éventuel de l'article>",
    "content_type": "text/html",
    "internal": false,
    "origin_by": "emily@example.com",
    "origin_by_id": 8,
    "created_at": "2020-11-13T14:34:35.318Z",
    "attachments": [
      {
        "id": 174,
        "filename": "message_vocal.mp3",
        "size": "35574",
        "preferences": { "Content-Type": "audio/mpeg", "Mime-Type": "audio/mpeg" },
        "url": "https://zammad.example.com/api/v1/ticket_attachment/81/104/174"
      }
    ],
    "accounted_time": 0
  }
}
```

### 4.2 Points clés pour le moteur

- **Attachments** : non inclus dans le payload, seul un **lien** est fourni
  (`article.attachments[].url`) pointant vers `/api/v1/ticket_attachment/<ticket_id>/<article_id>/<attachment_id>`.
  La récupération nécessite une **authentification** via l'API Zammad (token).
- **Toutes** données utilisateur sensibles sont **exclues** du payload : `last_login`,
  `login_failed`, `password`, `preferences`, `group_ids`, `groups`, `authorization_ids`, `authorizations`.
- Les objets `customer`, `owner`, `group`, `organization`, `priority` sont inclus (et
  peuvent être exploités pour identifier le client).

## 5. Déclenchement — Trigger

Le webhook doit être invoqué par un **trigger** (Admin → **Manage** → Triggers) :

1. **Nouveau trigger** : nom explicite, ex. `Transcrire message vocal`.
2. **Conditions** (déclenchement) :
   - `ticket.state_id` : ne pas déclencher sur les tickets fermés ;
   - `article.type` = `phone` (message vocal reçu par téléphone) ;
   - `article.attachments` non vide (présence du fichier audio) — condition paramétrable.
3. **Action** : sélectionner le webhook `zammad-auto-transcription` (action *deliver webhook*).

> Un trigger non-calibré risque de déclencher le webhook sur chaque article. Pour ne
> transcrire que les messages vocaux, affiner les conditions de type `phone` + attachment audio.

## 6. Contrats de réponses attendus par Zammad

| Réponse | Signification |
|---------|---------------|
| `200 OK` | traitement achevé — pas de renvoi |
| `4xx` | requête rejetée — pas de renvoi (log) |
| `5xx` | erreur serveur — Zammad peut retenter |

Notre endpoint doit répondre rapidement (le traitement lourd de transcription se fait en
arrière-plan), puis envoyer les mises à jour Zammad via l'API REST.

## 7. Sécurité

- Endpoint public derrière HTTPS (reverse proxy) : pas de clé dans le payload.
- Vérifier `X-Hub-Signature` (HMAC-SHA1, comparaison à temps constant) si secret configuré.
- Option Bearer Token pour bloquer les requêtes non autorisées.
- Rate limiting sur l'endpoint.
- **Ne jamais** logguer le secret, le token API Zammad ou le contenu du payload complet.

## 8. Références

Sources de validation :

- [Zammad Admin Docs — Adding Webhooks](https://admin-docs.zammad.org/en/latest/manage/webhook/add.html)
- [Zammad Admin Docs — Webhook Payload](https://admin-docs.zammad.org/en/latest/manage/webhook/payload.html)
- [Zammad Admin Docs — Webhook Examples / Triggers](https://admin-docs.zammad.org/en/latest/manage/webhook/examples/generic-notifications-trigger.html)