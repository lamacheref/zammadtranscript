# Roadmap

## Phase 1 — Fondations (POC)

- [ ] Réception d'un webhook Zammad (endpoint FastAPI)
- [ ] Téléchargement de l'attachment audio via l'API Zammad
- [ ] Transcription locale avec faster-whisper (format 3CX : `.mp3`, `.wav`, `.ogg`, `.m4a`)
- [ ] Mise à jour du titre du ticket via l'API Zammad

## Phase 2 — Intelligence locale

- [ ] Rédaction du titre et extraction du client via Ollama (LLM ≤ 3-4 Mds quantifié)
- [ ] Création de l'article de transcription dans le ticket
- [ ] Nettoyage du texte (numéros de téléphone, adresses, timestamps)

## Phase 3 — Robustesse & production

- [ ] Gestion des erreurs et des retries Zammad
- [ ] Idempotence (anti-double transcription)
- [ ] Sécurité : secret webhook, variables d'environnement, rate limiting
- [ ] Optimisation CPU/mémoire pour le LXC (quantification, threads)

## Phase 4 — Installation automatisée

- [ ] Script d'installation LXC au format community-scripts (`ct/` + `install/` + metadata)
- [ ] Tests en conditions réelles avec l'instance 3CX/Zammad