"""Téléchargement automatique du modèle Ollama configuré.

La progression est partagée entre l'API et le worker via Redis : l'UI affiche
une barre de progression, et le webhook fonctionne dès le premier lancement
même si le modèle n'a jamais été tiré.
"""

import json
import logging
import threading
import time

import httpx
import ollama

from .queue import get_redis_connection

logger = logging.getLogger(__name__)

PULL_KEY = "zat:pull:ollama"
LOCK_KEY = "zat:pull:ollama:lock"
LOCK_TTL = 2 * 60 * 60 + 60  # 2h01 : laisser le temps de télécharger un gros modèle

# Verrou en mémoire pour ne lancer qu'un seul thread de pull par processus.
_local_lock = threading.Lock()


def model_present(settings) -> bool:
    """Le modèle configuré est-il présent sur le serveur Ollama ?"""
    try:
        response = httpx.get(f"{settings.ollama_url}/api/tags", timeout=10)
        response.raise_for_status()
        names = {m.get("name", "").split(":")[0] for m in response.json().get("models", [])}
        return settings.ollama_model.split(":")[0] in names
    except Exception:
        return False


def get_download_status(settings) -> dict:
    """État du téléchargement en cours (lu depuis Redis), ou 'idle'."""
    conn = get_redis_connection(settings)
    try:
        raw = conn.get(PULL_KEY)
    except Exception as exc:
        return {"status": "error", "message": f"Redis injoignable : {exc}"}
    if not raw:
        return {"status": "idle", "message": "Aucun téléchargement en cours"}

    data = json.loads(raw)
    total = data.get("total") or 0
    completed = data.get("completed") or 0
    percent = round(completed / total * 100) if total else 0
    status = data.get("status")
    message = data.get("message") or ""
    if status == "done":
        return {"status": "done", "message": message or "Modèle téléchargé"}
    if status == "error":
        return {"status": "error", "message": message or "Téléchargement en échec"}
    return {
        "status": "downloading",
        "message": message or "Téléchargement…",
        "completed": completed,
        "total": total,
        "percent": percent,
    }


def start_model_download(settings) -> dict:
    """Lance le téléchargement du modèle s'il manque (dédupliqué par verrou Redis).

    Retourne 'started', 'in_progress' (déjà en cours ailleurs) ou 'present'.
    """
    if model_present(settings):
        return {"status": "present", "message": f"Modèle '{settings.ollama_model}' déjà présent"}

    conn = get_redis_connection(settings)
    acquired = conn.set(LOCK_KEY, "1", nx=True, ex=LOCK_TTL)
    if not acquired:
        return {"status": "in_progress", "message": "Un téléchargement est déjà en cours"}

    with _local_lock:
        threading.Thread(target=_pull_worker, args=(settings,), daemon=True).start()

    return {"status": "started", "message": f"Téléchargement de '{settings.ollama_model}' démarré"}


def ensure_ollama_model(settings, wait_timeout: float = 30 * 60) -> dict:
    """Attend que le modèle Ollama soit présent, en le téléchargeant si besoin.

    Retourne {"status": "ok"} quand le modèle est prêt. Appelé au démarrage
    (API + worker) et en filet de sécurité juste avant une génération de titre.
    """
    model = settings.ollama_model
    deadline = time.monotonic() + wait_timeout
    while time.monotonic() < deadline:
        try:
            if model_present(settings):
                return {"status": "ok", "message": f"Modèle '{model}' présent"}
            start_model_download(settings)
            while time.monotonic() < deadline:
                status = get_download_status(settings)
                if status["status"] == "done":
                    return {"status": "ok", "message": f"Modèle '{model}' téléchargé"}
                if status["status"] == "error":
                    return status
                time.sleep(2)
        except Exception as exc:
            logger.warning(
                "Téléchargement du modèle '%s' impossible pour l'instant (%s) — retry…",
                model,
                exc,
            )
            time.sleep(5)
    return {
        "status": "timeout",
        "message": f"Modèle '{model}' non téléchargé après {int(wait_timeout)}s",
    }


def ensure_ollama_model_in_background(settings) -> None:
    """Lance le téléchargement automatique au premier lancement, sans bloquer."""
    thread = threading.Thread(target=_ensure_safe, args=(settings,), daemon=True)
    thread.start()


def _ensure_safe(settings) -> None:
    try:
        result = ensure_ollama_model(settings)
        logger.info("Modèle Ollama : %s — %s", result["status"], result.get("message"))
    except Exception as exc:  # pragma: no cover - filet de sécurité
        logger.error("Vérification du modèle Ollama impossible : %s", exc)


def _pull_worker(settings) -> None:
    conn = get_redis_connection(settings)
    model = settings.ollama_model
    client = ollama.Client(host=settings.ollama_url)

    def push(status: str, message: str, completed=None, total=None) -> None:
        payload = {
            "status": status,
            "message": message,
            "model": model,
            "completed": completed,
            "total": total,
        }
        try:
            conn.set(PULL_KEY, json.dumps(payload), ex=30 * 60)
            conn.expire(LOCK_KEY, LOCK_TTL)
        except Exception as exc:
            logger.warning("Impossible de publier la progression du pull : %s", exc)

    logger.info("Téléchargement du modèle Ollama '%s'…", model)
    push("downloading", f"Téléchargement de {model}…")
    try:
        for progress in client.pull(model, stream=True):
            push(
                "downloading",
                getattr(progress, "status", "") or "Téléchargement…",
                getattr(progress, "completed", None),
                getattr(progress, "total", None),
            )
        push("done", f"Modèle {model} téléchargé")
        logger.info("Modèle Ollama '%s' téléchargé.", model)
    except Exception as exc:
        logger.error("Échec du téléchargement du modèle '%s' : %s", model, exc)
        push("error", str(exc))
    finally:
        try:
            conn.delete(LOCK_KEY)
        except Exception:
            pass
