import json
import logging

import ollama
from ollama import Client

from .config import Settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Tu es un assistant qui aide à archiver des messages vocaux de support client. "
    "Réponds uniquement en JSON valide, sans texte avant ou après."
)

USER_PROMPT_TEMPLATE = """Voici la transcription d'un message vocal laissé par un client.

Transcription :
{transcript}

Extrais :
1. "title" : un titre court de ticket (maximum 80 caractères), en français.
2. "customer_name" : le nom de la société ou de l'appelant si identifiable, sinon null.

Réponds uniquement avec un objet JSON JSON ayant cette forme exacte :
{{"title": "...", "customer_name": "..."}}
"""


class TitleError(Exception):
    pass


class TitleGenerator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: Client | None = None

    @property
    def client(self) -> Client:
        if self._client is None:
            self._client = ollama.Client(host=self.settings.ollama_url)
        return self._client

    def generate(self, transcript: str) -> dict:
        response = self.client.chat(
            model=self.settings.ollama_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PROMPT_TEMPLATE.format(transcript=transcript)},
            ],
            options={"num_predict": 256, "temperature": 0.2},
            format="json",
        )
        raw = response.message.content
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TitleError(f"Réponse LLM non JSON: {raw[:300]}") from exc

        title = str(data.get("title", "")).strip()
        customer = data.get("customer_name") or None
        if not title:
            raise TitleError("Le LLM n'a pas retourné de titre.")
        return {"title": title[:80], "customer_name": customer}
