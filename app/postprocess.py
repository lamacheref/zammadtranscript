import re

PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s.-]?)?(?:\d{2,4}[\s.-]?){2,}\d{2,4}(?![\d])")
TIMESTAMP_RE = re.compile(r"\b(?:\d{1,2}[:.]\d{2}(?:[:.]\d{2})?|(?:\d{1,2}:\d{2} [AP]M))\b")
URL_RE = re.compile(r"\b(?:https?://|www\.)\S+")


def clean_transcript(text: str) -> str:
    if not text:
        return ""
    text = URL_RE.sub(" ", text)
    text = PHONE_RE.sub(" <NUMERO>", text)
    text = TIMESTAMP_RE.sub(" ", text)
    text = re.sub(r"[\.,;:]+(?:[\s.,;:]+[\.,;:]+)+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
