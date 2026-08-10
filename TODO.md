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
- [x] Intégration Ollama pour le titre et l'extraction du client
- [x] Mise à jour Zammad : titre, client (`customer_id`), article de transcription
- [x] Idempotence + gestion des erreurs et retries

## Installation automatique du LXC (community-scripts)

> Basée sur le guide officiel :
> https://community-scripts.org/docs/contribution/templates_install/appname-install

### Préparation

- [ ] Forker/cloner le dépôt `community-scripts/ProxmoxVED`
  (ou utiliser le dossier `ProxmoxVED` : `ct/`, `install/`, metadata) dans ce projet
- [ ] Partir d'un script d'installation existant :
      `cp install/example-install.sh install/zammad-autotranscription-install.sh`

### Script d'installation (`install/zammad-autotranscription-install.sh`)

- [ ] En-tête conforme (copyright, `Author`, `License`, `Source`)
- [ ] `source /dev/stdin <<<"$FUNCTIONS_FILE_PATH"` + `color`, `verb_ip6`,
      `catch_errors`, `setting_up_container`, `network_check`, `update_os`
- [ ] Variables `var_*` avec guarded `read` (lisibles depuis les champs du site) :
      token API Zammad, URL Zammad, port du serveur, clé du LLM local, etc.
- [ ] Dependencies app-spécifiques uniquement (aucun doublon des paquets de base)
- [ ] Runtime via `tools.func` (`setup_uv` avec Python 3.12, etc.)
- [ ] Déploiement de l'application (clone du dépôt + fichiers)
- [ ] Configuration via heredoc unique (`.env` : `ZAMMAD_URL`, `ZAMMAD_TOKEN`,
      `WEBHOOK_SECRET`, modèle Whisper/LLM, port)
- [ ] Génération des secrets avec `openssl` (alphanumérique) + `chown`/`chmod` minimaux
- [ ] Service systemd (`after=network.target`, `Restart=on-failure`) activé au boot
- [ ] Finalisation : `motd_ssh`, `customize`, `cleanup_lxc`

### Script CT (`ct/zammad-autotranscription.sh`)

- [ ] Script conteneur conforme au modèle CT de community-scripts
- [ ] `export var_*` vers le conteneur (alignés avec l'install script)
- [ ] `FUNCTIONS_FILE_PATH` fourni à l'install script (jamais de curl vers `.func`)
- [ ] `update_script()` : gestion des mises à jour de l'application

### Métadonnées (site community-scripts)

- [ ] Déclaration `app_vars` (champs affichés sur le site + valeurs transmises)
- [ ] `install_method` associé (metadata + PocketBase)

### Tests

- [ ] Test local : `bash ct/zammad-autotranscription.sh` (zéro config)
- [ ] Test après push : `bash -c "$(curl -fsSL <url-raw>/ct/zammad-autotranscription.sh)"`
- [ ] Vérifier contraintes LXC CPU only (RAM, threads, pas de GPU)

## Divers

- [ ] Lint/validation du code (ruff ou équivalent)
- [ ] README : instructions d'installation LXC via communauté scripts