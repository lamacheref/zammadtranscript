# Spécifications — Envoi des messages vocaux 3CX

Rédaction de la tâche « Documenter la configuration 3CX (format/envoi des messages vocaux) »
du `TODO.md`. Ce document décrit la configuration de l'instance 3CX pour acheminer les
messages vocaux vers un ticket Zammad, ainsi que le format des fichiers audio attendus.

## 1. Principe

3CX dépose un message vocal (répondeur) et l'envoie par courriel à une adresse surveillée
par Zammad. Le canal **e-mail** de Zammad reçoit le courriel et crée un ticket avec le
fichier audio en **pièce jointe**. Le webhook (voir `documentations/zammad-webhook.md`)
déclenche ensuite la transcription.

```
Appel manqué / non répondu
        │
        ▼
3CX  ──►  répondeur (voicemail)  ──►  e-mail + pièce jointe audio
        │                                   │
        │                          Zammad canal e-mail
        │                                   │
        │                          ticket créé + attachment
        │                                   │
        └──────────► webhook /webhook/zammad ◄──┘
                        (transcription)
```

## 2. Configuration 3CX — envoi des messages vocaux

### 2.1 Options générales système

Management Console → **System** → **Voicemail** :

| Paramètre | Valeur recommandée | Rôle |
|-----------|---------------------|------|
| Voicemail menu extension | ex. `999`/`9999` | numéro d'accès au menu vocal |
| Do not save voicemails less than (s) | ≥ `2` | filtre les messages trop courts |
| Voicemail quota | adapté à la volumétrie | stockage des fichiers |
| Automatically delete voicemails older than | ex. `30` jours | rotation des fichiers |

### 2.2 Acheminement par extension / poste

Le message vocal doit être transmis à Zammad pour chaque poste concerné.

Management Console → **Extensions** → poste → **Voicemail** :

1. Ouvrir les paramètres du répondeur du poste.
2. Activer l'envoi du message vocal par e-mail (ex. *« Send voicemail to email »* /
   *« Email notification with voicemail »*, libellé selon version).
3. Renseigner l'adresse de destination : l'adresse du **canal e-mail de Zammad**
   (ex. `support@domain.example`).
4. Activer l'envoi de la **pièce jointe** audio (attachment) — option *Attach voicemail*.
5. (Facultatif) Conserver une copie dans la boîte vocale.

> Pour une diffusion « groupe » (ex. support), configurer la boîte vocale du groupe/destination
> ou la file d'appel de la même façon.

### 2.3 Serveur SMTP sortant

L'e-mail de notification est envoyé par 3CX via son SMTP intégré. Paramètres associés :

- Vérifier que l'envoi SMTP sortant fonctionne (Management Console → **Settings**).
- S'assurer que l'adresse d'expéditeur 3CX (ex. `noreply@...`) est **autorisée/whitelistée**
  dans Zammad (anti-spam, SPF/DKIM si déployé) pour ne pas être bloquée.

## 3. Format des fichiers audio

### 3.1 Formats produits par 3CX

| Forme | Format courant | Remarques |
|-------|----------------|-----------|
| Message vocal (voicemail) | `.wav` (PCM 8000 Hz, mono) | format par défaut historique de 3CX |
| Selon version/configuration | `.ogg`, `.mp3` | certaines versions/paramètres fournissent ces formats |
| Greetings | `.wav` PCM 8000 Hz 16 bits mono | exigences 3CX |
| Enregistrements CFD | `.wav` | ex. rappel d'un projet Call Flow Designer |

### 3.2 Zammad — pièce jointe

- L'audio arrive dans le ticket en tant qu'**attachment** (`article.attachments[]`).
- Le webhook ne contient **pas** le fichier ; il fournit une URL Zammad du type
  `/api/v1/ticket_attachment/<ticket_id>/<article_id>/<attachment_id>` (voir
  `documentations/zammad-webhook.md`).
- Le moteur de transcription doit supporter : **`.mp3`, `.wav`, `.ogg`, `.m4a`**
  (aligné sur `PROJET.md`), via conversion `ffmpeg` si nécessaire (mono, 16 kHz).

## 4. Type d'article dans Zammad

- Le message vocal arrivé par e-mail engendre un article de type **`email`** (canal e-mail),
  contrairement au type `phone` cité dans `zammad-webhook.md` (cas d'un envoi direct via API).
- Conséquence pour le **trigger** Zammad : privilégier une condition fondée sur la
  **présence d'un attachment audio** plutôt qu'uniquement sur `article.type`, afin de
  couvrir les deux canaux.

## 5. Vérifications et tests

1. Laisser un message radio (répondeur) sur un poste configuré.
2. Contrôler la réception du courriel dans la boîte Zammad (canal e-mail) : sujet, expéditeur, pièce jointe.
3. Vérifier la création du ticket et le positionnement du webhook (headers
   `X-Zammad-Trigger`, `X-Zammad-Delivery`, `X-Hub-Signature`).
4. Confirmer que la transcription est bien envoyée sur le ticket (titre, client, texte).

## 6. Références

- Étant donné la variabilité selon la version 3CX (ex. V18/V20), valider les libellés
  d'interface dans le Management Console de l'instance réelle :
  - Paramètres de répondeur par extension (envoi e-mail + pièce jointe).
  - Paramètres systèmes voicemail.
- Formats audio 3CX : `wav` (PCM 8000 Hz mono) par défaut, `ogg`/`mp3` selon config.