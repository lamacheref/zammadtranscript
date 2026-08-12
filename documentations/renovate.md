# Automatisation des mises à jour de dépendances (Renovate)

Ce document décrit la configuration Renovate du projet et son installation.
Renovate est préféré à Dependabot car le projet est hébergé en parallèle sur
Gitea et GitHub : Renovate fonctionne sur les deux forges.

## Fichier de configuration

`renovate.json` à la racine du dépôt :

- **Managers détectés automatiquement** : `requirements.txt` (pip), `Dockerfile`
  et `docker-compose.yml` (Docker), GitHub Actions.
- **Planification** : une fois par semaine (heure Europe/Paris).
- **Regroupement** des changements `minor`/`patch` en une seule PR par manager
  (Python, Docker), réduisant le bruit.
- **Dashboard des dépendances** (`:dependencyDashboard`) pour suivre et
  approuver les mises à jour majeures.
- **Alerts sécurité** : PR immédiate avec le label `security`.
- **Labels** : `dependencies` sur chaque PR.
- **Commits sémantiques** (`:semanticCommitScope(deps)`) alignés sur la
  convention de commit du dépôt.

## Installation

### GitHub (app hébergée par Mend)

1. Ouvrir https://github.com/apps/renovate et cliquer sur **Install**.
2. Choisir le compte/organisation, puis le dépôt `zammadtranscript`.
3. Accorder les permissions demandées (lecture/écriture sur le dépôt,
   statuses, webhooks).
4. Le premier run crée le *Dependency Dashboard* et les PR proposées.

Aucune action supplémentaire : la configuration se trouve dans le dépôt.

### Gitea (self-hosted, recommandé)

Renovate n'est pas disponible en app hébergée sur Gitea ; il faut l'exécuter
soi-même. Deux options :

#### Option 1 : conteneur (Docker)

```bash
docker run --rm \
  -e LOG_LEVEL=info \
  -e RENOVATE_PLATFORM=gitea \
  -e RENOVATE_ENDPOINT=https://gitea.smiden.eu/api/v1/ \
  -e RENOVATE_TOKEN=<TOKEN> \
  -e RENOVATE_REPOSITORIES=flamachere/zammadtranscript \
  -v "$PWD/renovate.json:/usr/src/app/config.json" \
  renovate/renovate:latest
```

- `<TOKEN>` : token Gitea avec droits `write:repository`, `read:user` et
  `write:issue` (création des PR/issues du dashboard).
- `https://gitea.smiden.eu/api/v1/` est l'endpoint à adapter à l'instance Gitea.
- La config étant lue depuis le dépôt (priorité au fichier du dépôt), le
  fichier monté dans `config.json` peut être vide (`{}`) — il sert uniquement à
  permettre le lancement.

#### Option 2 : Cron (système / CI de Gitea)

Exécuter la commande ci-dessus via cron (ex. hebdomadaire) :

```
0 3 * * 1 docker run --rm -e ... renovate/renovate:latest
```

Pour piloter la planification côté Renovate, la config utilise déjà
`"schedule": ["before 6am on the first day of the week"]` ; le cron peut donc
passer `--token` sans double planification (Renovate ne crée des PR que selon
son propre `schedule`).

## Workflow

1. **GitHub** : l'app Renovate détecte `renovate.json` et ouvre chaque semaine
   une PR groupée par manager, validée par la CI (tests + lint).
2. **Gitea** : le bot self-hosted produit les mêmes PR sur la forge Gitea.
3. Après revue (et passage des checks CI), les PR sont mergées ; le versionnage
   automatique de la CI continue de s'appliquer normalement.

> Remarque : les deux forges sont des miroirs l'un de l'autre. Il est conseillé
> de n'activer Renovate que sur une seule forge (ex. Gitea) et de laisser la
> fusion se propager via le miroir, afin d'éviter les conflits de PR
> concurrentes.