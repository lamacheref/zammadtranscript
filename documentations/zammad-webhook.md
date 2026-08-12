# Spécifications — Webhook Zammad

Rédaction de la tâche « Décrire la configuration webhook dans Zammad (événements, URL, secret) »
du `TODO.md`. Ce document spécifie la configuration webhook côté Zammad et les
données reçues par notre moteur de transcription.

> **Interface utilisée : Zammad en français.** Les libellés de cet écran sont
> donnés en français (traduction officielle du catalogue `zammad.fr-fr.po`),
> avec — quand c'est utile — le libellé anglais d'origine entre parenthèses.

## 1. Principe

Zammad envoie un webhook HTTP POST vers notre serveur (`/webhook/zammad`) lorsqu'un
ticket/article est créé (message vocal 3CX reçu dans un ticket). Le webhook est
déclenché via un **déclencheur** (*trigger*) qui sélectionne le webhook à utiliser.

## 2. Configuration côté Zammad

### 2.1 Navigation

1. Dans la barre supérieure (ou le menu utilisateur en bas à gauche avec l'ancienne
   interface), cliquer sur **Administration** (icône engrenage ⚙).
2. Dans la page d'administration, la barre latérale affiche les sections de gestion.
   Ouvrir la catégorie **Gérer** (*Manage*).
3. Cliquer sur **Webhooks** dans la section **Gérer**.
4. Cliquer sur le bouton **Nouveau webhook** (*New Webhook*) en haut à droite de la liste.

> Accès direct par URL : `https://<votre-zammad>/#manage/webhook`
> (chemin interne constant `#manage/webhook`, quel que soit l'habillage de la barre latérale).

### 2.2 Champs du webhook

Le formulaire **Nouveau webhook** présente les champs suivants (libellés français de l'interface) :

| Champ (interface FR) | Valeur recommandée pour ce projet |
|----------------------|-----------------------------------|
| **Nom** (*Name*) | `zammad-auto-transcription` |
| **Point de terminaison** (*Endpoint*) | `https://<hôte-transcription>/webhook/zammad` |
| **Méthode de la requête** (*Request Method*) | `POST` |
| **Vérification du certificat SSL** (*SSL verification*) | `Oui` (si certificat valide) |
| **Connexion** (*Authentication*) | `Bearer Token` — voir § 2.3 |
| **Signature HMAC SHA1 du jeton** (*HMAC SHA1 Signature Token*) | renseigner le secret — voir § 2.4 |
| **Charge utile (payload) personnalisée** (*Custom Payload*) | `off` (utiliser le payload par défaut) |
| **Note** (*Note*) | (facultatif) `Transcription des messages vocaux 3CX` |
| **Actif** (*Active*) | `Oui` (activé) |

> Zammad ignore les paramètres d'authentification basique passés dans l'URL de l'endpoint ;
> l'authentification se configure via les champs dédiés ci-dessous.

### 2.3 Connexion / Authentification (Bearer Token)

Le serveur de transcription peut exiger un bearer token. Configuration :

1. **Connexion** (*Authentication*) = `Bearer Token`.
2. Renseigner **Bearer Token** : le token attendu par le serveur.
3. Zammad l'enverra dans le header `Authorization: Bearer <token>`.

> Autres valeurs possibles : **Authentification HTTP de base** (*HTTP Basic Authentication*)
> puis **Nom d'utilisateur** / **Mot de passe**, ou aucune authentification.

### 2.4 Signature (secret)

- Zammad accepte un **Signature HMAC SHA1 du jeton** (*HMAC SHA1 Signature Token*) : si
  renseigné, **toutes** les requêtes webhook contiennent le header `x-hub-signature`
  (`UserAgent.set_signature` ajoute `X-Hub-Signature: sha1=<hex>`).
- Ce secret ne chiffre **pas** le payload : il fournit une signature HMAC-SHA1 du corps de
  la requête permettant de vérifier l'origine. **Ne pas diffuser le secret en clair.**
- Le serveur doit comparer la signature à l'aide d'une comparaison à temps constant
  (`hmac.compare_digest` en Python).

## 3. En-têtes de requête (headers)

Zammad envoie systématiquement (source : `lib/user_agent.rb` + `app/jobs/trigger_webhook_job.rb`) :

| Header | Contenu |
|--------|---------|
| `Content-Type` | `application/json; charset=utf-8` |
| `User-Agent` | `Zammad User Agent` |
| `X-Zammad-Trigger` | nom du déclencheur qui a déclenché l'envoi |
| `X-Zammad-Delivery` | `job_id` unique de l'envoi (identifiant du job DelayedJob) |
| `X-Hub-Signature` | `sha1=<hex>` — signature HMAC-SHA1 du corps (si secret configuré) |
| `Authorization` | `Bearer <token>` (si connexion = Bearer Token) |

## 4. Payload par défaut (JSON)

Si `Custom Payload` est désactivé, Zammad envoie le payload par défaut
(`TriggerWebhookJob::RecordPayload`). Il contient l'objet `ticket` complet et l'objet
`article` (article créateur), avec les données utilisateur sensibles **exclues**.

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
    "owner_id": 5,
    "group_id": 3,
    "organization_id": 3,
    "priority_id": 2,
    "customer": { "id": 8, "firstname": "Emily", "lastname": "Adams", "email": "emily@example.com", "organization": "Awesome Customer Inc.", "...": "..." },
    "owner": { "id": 5, "firstname": "Emma", "lastname": "Taylor", "...": "..." },
    "created_by": { "...": "..." },
    "updated_by": { "...": "..." },
    "organization": { "id": 3, "name": "Awesome Customer Inc.", "...": "..." },
    "priority": { "id": 2, "name": "2 normal", "...": "..." },
    "group": { "id": 3, "name": "Service Desk", "...": "..." },
    "created_at": "2020-11-13T14:34:35.282Z",
    "updated_at": "2020-11-13T14:34:35.333Z",
    "...": "autres champs du ticket (custom objects éventuels inclus)"
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
    "created_by": { "...": "..." },
    "updated_by": { "...": "..." },
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

### 4.2 Points clés pour le moteur (validate on source)

- **Attachments** : non inclus dans le payload, seul un **lien** est fourni
  (`article.attachments[].url`), construit par le serveur à partir du champ système
  `http_type` + `fqdn` :
  `<http://|https://><fqdn>/api/v1/ticket_attachment/<ticket_id>/<article_id>/<attachment_id>`.
  La récupération nécessite une **authentification** via l'API Zammad (token).
- **Données utilisateur exclues** (`USER_ATTRIBUTE_FILTER`) : `last_login`,
  `login_failed`, `password`, `preferences`, `group_ids`, `groups`,
  `authorization_ids`, `authorizations`.
- Les associations du **ticket** incluses : `owner`, `customer`, `created_by`,
  `updated_by`, `organization`, `priority`, `group`. Celles de l'**article** :
  `created_by`, `updated_by`.
- `article.accounted_time` : temps de travail associé (comptabilité de temps), `0.0` sinon.
- `created_at` / `updated_at` : dates au format ISO 8601 (UTC, `Z`).

## 5. Déclenchement — Déclencheur (Trigger)

Le webhook doit être invoqué par un **déclencheur** (**Administration → Gérer → Déclencheurs**, route `#manage/trigger`).

### 5.1 Création du déclencheur

1. Ouvrir **Administration → Gérer → Déclencheurs** (route `#manage/trigger`).
2. Cliquer sur **Nouveau déclencheur** (*New Trigger*).
3. **Nom** : saisissez un nom explicite, ex. `Transcrire message vocal`.
4. **Activé par** (*Activated by*) : **Action** (valeur par défaut) — les déclencheurs temporels (*Time event*) ne conviennent pas pour réagir à la réception d'un message vocal.
5. **Exécution de l'action** (*Action execution*) : **Conditionnelle (par défaut)** (*Selective (default)*) — le déclencheur ne s'exécute que si au moins un champ des conditions a changé et que les conditions correspondent.
6. **Actif** : coché (valeur par défaut).

### 5.2 Configuration des conditions

Cliquer sur **Conditions pour les éléments concernés** (*Conditions for affected objects*). Le sélecteur de tickets propose deux modes :

- **Mode simple** : une liste plate de conditions liées par **Correspondance totale (AND)** (*Match all (AND)*). Suffisant pour la plupart des cas.
- **Mode expert** (bouton **Mode expert** activé) : permet des sous-clauses avec **Correspondance partielle (OR)** (*Match any (OR)*) ou **Aucune correspondance (NOT)** (*Match none (NOT)*), et l'opérateur **a été modifié** (*has changed*) sur les attributs.

> **Recommandation** : activer le **Mode expert** pour bénéficier de l'opérateur **a été modifié** (*has changed*) sur `ticket.action`, ce qui évite de retriggerer sur des mises à jour non pertinentes.

Créer les conditions suivantes (chaque ligne = un attribut du sélecteur) :

| Groupe | Attribut (libellé FR) | Opérateur | Valeur | Rationale |
|--------|------------------------|-----------|--------|-----------|
| **Ticket** | **Action** (*action*) | **est** (*is*) | **créé** (*created*) | Ne déclencher qu'à la création du ticket/article, pas aux mises à jour ultérieures. |
| **Ticket** | **État** (*state_id*) | **n'est pas** (*is not*) | **Fermés** (*Closed*) | Ignorer les tickets déjà clos. |
| **Article** | **Type** (*type_id*) | **est** (*is*) | **Téléphone** (*Phone*) | Les messages vocaux 3CX arrivent comme articles de type *Phone* (identifiant interne `phone`). |
| **Article** | **Pièces jointes** (*has_attachments*) | **est** (*is*) | **Oui** (*oui*) | Garantir la présence d'un fichier audio (champ booléen `has_attachments` du modèle `Ticket::Article`). |

> L'opérateur **a été modifié** (*has changed*) est disponible uniquement en **Mode expert** sur les attributs supportés (ex. `ticket.action`, `ticket.state_id`). Il évite de retriggerer sur des modifications non pertinentes (ex. changement de priorité uniquement).

> L'opérateur **Correspondance partielle (OR)** permet d'alterner entre plusieurs valeurs (ex. `article.type` est *Phone* **OU** *Note* avec pièce jointe).

### 5.3 Configuration de l'action

1. Dans la boîte **Appliquer les modifications sur les objets** (*Execute changes on objects*), développer le groupe **Notification**.
2. Sélectionner **Webhook** (*Webhook*).
3. Dans la liste déroulante **Webhook**, choisir `zammad-auto-transcription` (le webhook créé en § 2).
4. Cliquer sur **Enregistrer** (*Save*).

### 5.4 Validation rapide

1. Ouvrir à nouveau le déclencheur → vérifier que **Actif** est coché.
2. Effectuer un appel test 3CX vers la file Zammad → vérifier que l'article créé porte **Type = Téléphone** et possède une **Pièce jointe**.
3. Surveiller les logs de l'application de transcription (endpoint `POST /webhook/zammad` → `202 Accepted` → job enfile → worker traite).
4. En cas de doute, consulter l'historique des déclencheurs (*Trigger history*) et les logs de la file RQ (`docker logs zammad-worker`).

> **Conseil** : si le webhook ne se déclenche pas, vérifier que le déclencheur est **Actif** et que les conditions correspondent exactement (opérateur **est** / **n'est pas**, valeurs exactes `phone`/`oui`).

## 6. Contrats de réponses attendus par Zammad

Le job `TriggerWebhookJob` considère la requête comme réussie dès qu'il reçoit une réponse
**HTTP 2xx** ; sinon il relance `TriggerWebhookJob` (retry) jusqu'à **5 tentatives** avec un
backoff de `10s × n° d'exécution` (10 s, 20 s, 30 s, 40 s puis abandon).

| Réponse | Comportement Zammad |
|---------|---------------------|
| `2xx` (ex. `200 OK`, `202 Accepted`) | traitement achevé — pas de renvoi |
| `4xx` | requête rejetée — **retentée** (retry 5×, backoff 10s×n) |
| `5xx` | erreur serveur — **retentée** (retry 5×, backoff 10s×n) |
| Erreur réseau/timeout | **retentée** (idem) |

Notre endpoint doit donc répondre rapidement avec un statut `2xx` (le traitement lourd de
transcription se fait en arrière-plan), puis envoyer les mises à jour Zammad via l'API REST.

## 7. Sécurité

- Endpoint public derrière HTTPS (reverse proxy) : pas de clé dans le payload.
- Vérifier `X-Hub-Signature` (`sha1=<hex>`, comparaison à temps constant) si secret configuré.
- Option Bearer Token pour bloquer les requêtes non autorisées.
- Rate limiting sur l'endpoint.
- **Ne jamais** logguer le secret, le token API Zammad ou le contenu du payload complet.

## 8. Références

Sources de validation (traductions officielles `i18n/zammad.fr-fr.po` + code source) :

- [Zammad Admin Docs — Adding Webhooks](https://admin-docs.zammad.org/en/latest/manage/webhook/add.html)
- [Zammad Admin Docs — Webhook Payload](https://admin-docs.zammad.org/en/latest/manage/webhook/payload.html)
- [Zammad Admin Docs — Webhook Examples / Triggers](https://admin-docs.zammad.org/en/latest/manage/webhook/examples/generic-notifications-trigger.html)
- Code source : `app/assets/javascripts/app/models/webhook.coffee`
  (champs du formulaire), `app/jobs/trigger_webhook_job.rb` et `lib/user_agent.rb`
  (headers, payload, retries)