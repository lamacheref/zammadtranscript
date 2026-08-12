import httpx

from .config import Settings


class ZammadError(Exception):
    pass


class ZammadClient:
    def __init__(self, settings: Settings):
        self.base_url = settings.zammad_url.rstrip("/")
        self.token = settings.zammad_token
        self.timeout = settings.zammad_timeout

    def _headers(self, accept_json: bool = False) -> dict[str, str]:
        headers = {"Authorization": f"Token token={self.token}"}
        if accept_json:
            headers["Accept"] = "application/json"
        return headers

    def get_attachment(self, url: str) -> bytes:
        response = httpx.get(url, headers=self._headers(), timeout=self.timeout)
        response.raise_for_status()
        return response.content

    def get_ticket(self, ticket_id: int) -> dict:
        return self._get(f"/api/v1/tickets/{ticket_id}")

    def get_article(self, ticket_id: int, article_id: int) -> dict:
        return self._get(f"/api/v1/tickets/{ticket_id}/articles/{article_id}")

    def get_ticket_articles(self, ticket_id: int) -> list:
        # Endpoint Zammad : GET /api/v1/ticket_articles/by_ticket/{ticket_id}
        return self._get(f"/api/v1/ticket_articles/by_ticket/{ticket_id}")

    def update_ticket(self, ticket_id: int, payload: dict) -> dict:
        return self._put(f"/api/v1/tickets/{ticket_id}", payload)

    def create_article(self, ticket_id: int, payload: dict) -> dict:
        return self._post(f"/api/v1/tickets/{ticket_id}/articles", payload)

    def find_user_by_name(self, name: str) -> dict | None:
        try:
            result = self._get(f"/api/v1/users/search?query={name}")
            users = result if isinstance(result, list) else result.get("users", [])
            for user in users:
                fullname = f"{user.get('firstname', '')} {user.get('lastname', '')}".strip()
                if (
                    fullname.lower() == name.lower()
                    or user.get("email", "").lower() == name.lower()
                ):
                    return user
            return None
        except ZammadError:
            return None

    def find_user_by_phone(self, phone: str) -> dict | None:
        """Recherche un utilisateur Zammad par numéro de téléphone."""
        try:
            result = self._get(f"/api/v1/users/search?query={phone}")
            users = result if isinstance(result, list) else result.get("users", [])
            for user in users:
                for field in ("phone", "mobile", "fax"):
                    if user.get(field) and phone in user[field]:
                        return user
            return None
        except ZammadError:
            return None

    def create_user(self, firstname: str, lastname: str, email: str | None = None) -> dict:
        payload = {"firstname": firstname, "lastname": lastname}
        if email:
            payload["email"] = email
        return self._post("/api/v1/users", payload)

    def find_ticket_by_number(self, number: str) -> dict | None:
        """Recherche un ticket par son numéro (champ 'number' de Zammad)."""
        try:
            # Zammad search endpoint for tickets
            result = self._get(f"/api/v1/tickets/search?query=number:{number}")
            tickets = result if isinstance(result, list) else result.get("tickets", [])
            if tickets:
                return tickets[0]
            return None
        except ZammadError:
            return None

    def _get(self, path: str) -> dict:
        return self._request("GET", path)

    def _put(self, path: str, payload: dict) -> dict:
        return self._request("PUT", path, json=payload)

    def _post(self, path: str, payload: dict) -> dict:
        return self._request("POST", path, json=payload)

    def _request(self, method: str, path: str, json: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        try:
            response = httpx.request(
                method,
                url,
                headers=self._headers(accept_json=True),
                json=json,
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise ZammadError(f"Requête Zammad échouée ({method} {url}): {exc}") from exc
        if response.status_code >= 400:
            raise ZammadError(
                f"Zammad a répondu {response.status_code} pour {method} {url}: {response.text[:500]}"
            )
        return response.json()
