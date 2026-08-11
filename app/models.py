from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class Attachment(StrictModel):
    id: int | None = None
    filename: str | None = None
    size: str | None = None
    url: str | None = Field(default=None, description="URL Zammad de l'attachment")
    preferences: dict[str, Any] = {}


class Article(StrictModel):
    id: int | None = None
    ticket_id: int | None = None
    type: str | None = None
    sender: str | None = None
    body: str | None = None
    attachments: list[Attachment] = []
    created_at: str | None = None


class Ticket(StrictModel):
    id: int | None = None
    number: str | None = None
    title: str | None = None
    state: str | None = None
    customer_id: int | None = None
    customer: dict[str, Any] | None = None
    group: dict[str, Any] | None = None


class WebhookPayload(StrictModel):
    ticket: Ticket = Field(default_factory=Ticket)
    article: Article = Field(default_factory=Article)


class ProcessingResult(BaseModel):
    ticket_id: int
    article_id: int | None = None
    transcript: str | None = None
    title: str | None = None
    customer_id: int | None = None


class TranscribeRequest(BaseModel):
    ticket_id: int