# Rapport de couverture de tests

Rapport généré à partir de la suite de tests pytest du projet Zammad-Auto-Transcription.

## Résumé

| Indicateur | Valeur |
|---|---|
| Total tests | 73 |
| Tests réussis | 73 |
| Tests échoués | 0 |
| Couverture globale | **97 %** |
| Seuil exigé (CI) | 80 % |
| Commande | `python -m pytest --cov=app --cov-report=term-missing tests/` |

La couverture globale est de **97 %**, largement au-dessus du seuil de 80 % imposé par le CI/CD. Un seul avertissement (dépréciation interne à Starlette) est signalé, sans impact sur les tests.

## Couverture par module

| Module | Lignes | Non couvertes | Couverture | Lignes non couvertes |
|---|---|---|---|---|
| `app/__init__.py` | 4 | 0 | 100 % | — |
| `app/config.py` | 24 | 0 | 100 % | — |
| `app/logging_config.py` | 14 | 0 | 100 % | — |
| `app/main.py` | 96 | 9 | 91 % | 36, 43-44, 86-89, 164-166 |
| `app/models.py` | 35 | 0 | 100 % | — |
| `app/postprocess.py` | 13 | 1 | 92 % | 10 |
| `app/processor.py` | 103 | 0 | 100 % | — |
| `app/queue.py` | 22 | 0 | 100 % | — |
| `app/title_generator.py` | 31 | 0 | 100 % | — |
| `app/transcriber.py` | 34 | 0 | 100 % | — |
| `app/worker.py` | 21 | 5 | 76 % | 28-32 |
| `app/zammad.py` | 59 | 0 | 100 % | — |
| **Total** | **456** | **15** | **97 %** | |

## Répartition des tests par fichier

| Fichier de tests | Nombre de tests | Couvre |
|---|---|---|
| `tests/test_bump_version.py` | 11 | Script de versionnement (`scripts/bump_version.py`) |
| `tests/test_webhook.py` | 18 | Endpoints webhook/UI, signature HMAC, autorisation |
| `tests/test_zammad.py` | 14 | Client API Zammad |
| `tests/test_processor.py` | 12 | Pipeline, idempotence, retries, résolution client |
| `tests/test_title_generator.py` | 6 | Génération de titre / extraction client (LLM) |
| `tests/test_transcriber.py` | 5 | Transcriber (ffmpeg, whisper, modèles) |
| `tests/test_queue.py` | 4 | File RQ (Redis), job de traitement |
| `tests/test_logging.py` | 2 | Configuration du logging centralisé |
| `tests/test_worker.py` | 1 | Point d'entrée du worker RQ |

## Lignes non couvertes (détail)

Les lignes non couvertes concernent des branches marginales, difficiles ou volontairement non testées :

- **`app/main.py`** : cas d'erreur du bloc `except` de la validation de signature, branche de la fonction d'autorisation sans header `Authorization`, et le bloc `if __name__ == "__main__"` (lancement direct).
- **`app/postprocess.py`** (ligne 10) : branche d'entrée vide (`if not text: return ""`).
- **`app/worker.py`** (lignes 28-32) : bloc `if __name__ == "__main__"` et gestion `KeyboardInterrupt`.

Aucune de ces branches ne couvre de logique métier critique ; elles sont écartées du seuil car non pertinentes à tester en isolation.

## Intégration CI/CD

La validation qualité fait partie du pipeline GitHub Actions :

1. **Lint** : `ruff check` + `ruff format --check` sur `app/`, `scripts/`, `tests/`.
2. **Tests** : `pytest --cov=app --cov-fail-under=80 --cov-report=term-missing tests/`.
3. Le job **version** n'est déclenché que si les tests passent (minor/fix selon les commits `feat:`).

Un échec de lint ou une couverture inférieure à 80 % bloque le build et la mise à jour de version.

---

# Test Coverage Report

Report generated from the pytest test suite of the Zammad-Auto-Transcription project.

## Summary

| Metric | Value |
|---|---|
| Total tests | 73 |
| Passed | 73 |
| Failed | 0 |
| Global coverage | **97 %** |
| Required threshold (CI) | 80 % |
| Command | `python -m pytest --cov=app --cov-report=term-missing tests/` |

Global coverage is **97 %**, well above the 80 % threshold enforced by CI/CD. Only one warning (an internal Starlette deprecation) is reported, with no impact on the tests.

## Coverage by module

| Module | Statements | Missed | Coverage | Missed lines |
|---|---|---|---|---|
| `app/__init__.py` | 4 | 0 | 100 % | — |
| `app/config.py` | 24 | 0 | 100 % | — |
| `app/logging_config.py` | 14 | 0 | 100 % | — |
| `app/main.py` | 96 | 9 | 91 % | 36, 43-44, 86-89, 164-166 |
| `app/models.py` | 35 | 0 | 100 % | — |
| `app/postprocess.py` | 13 | 1 | 92 % | 10 |
| `app/processor.py` | 103 | 0 | 100 % | — |
| `app/queue.py` | 22 | 0 | 100 % | — |
| `app/title_generator.py` | 31 | 0 | 100 % | — |
| `app/transcriber.py` | 34 | 0 | 100 % | — |
| `app/worker.py` | 21 | 5 | 76 % | 28-32 |
| `app/zammad.py` | 59 | 0 | 100 % | — |
| **Total** | **456** | **15** | **97 %** | |

## Tests breakdown by file

| Test file | Number of tests | Covers |
|---|---|---|
| `tests/test_bump_version.py` | 11 | Versioning script (`scripts/bump_version.py`) |
| `tests/test_webhook.py` | 18 | Webhook/UI endpoints, HMAC signature, authorization |
| `tests/test_zammad.py` | 14 | Zammad API client |
| `tests/test_processor.py` | 12 | Pipeline, idempotency, retries, customer resolution |
| `tests/test_title_generator.py` | 6 | Title generation / customer extraction (LLM) |
| `tests/test_transcriber.py` | 5 | Transcriber (ffmpeg, whisper, models) |
| `tests/test_queue.py` | 4 | RQ queue (Redis), processing job |
| `tests/test_logging.py` | 2 | Centralized logging configuration |
| `tests/test_worker.py` | 1 | RQ worker entry point |

## Uncovered lines (detail)

The uncovered lines concern marginal branches, either hard to reach or intentionally not tested:

- **`app/main.py`**: error branch of the signature validation `except`, the authorization function path without an `Authorization` header, and the `if __name__ == "__main__"` block (direct launch).
- **`app/postprocess.py`** (line 10): empty input branch (`if not text: return ""`).
- **`app/worker.py`** (lines 28-32): `if __name__ == "__main__"` block and `KeyboardInterrupt` handling.

None of these branches cover critical business logic; they are excluded from the threshold as they are not relevant to test in isolation.

## CI/CD integration

Quality validation is part of the GitHub Actions pipeline:

1. **Lint**: `ruff check` + `ruff format --check` on `app/`, `scripts/`, `tests/`.
2. **Tests**: `pytest --cov=app --cov-fail-under=80 --cov-report=term-missing tests/`.
3. The **version** job only runs if tests pass (minor/fix based on `feat:` commits).

A lint failure or coverage below 80 % blocks the build and the version bump.
