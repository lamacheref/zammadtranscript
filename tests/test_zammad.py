from unittest.mock import patch

import httpx
import pytest

from app.config import Settings
from app.zammad import ZammadClient, ZammadError


def make_client(**overrides):
    base = {"zammad_url": "http://zammad.example.com", "zammad_token": "t0k3n"}
    base.update(overrides)
    return ZammadClient(Settings(**base))


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    @property
    def content(self):
        return self.payload.encode()

    @property
    def text(self):
        return self.payload

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=self)


@patch("app.zammad.httpx.request")
def test_get_ticket_success(mock_request):
    client = make_client()
    mock_request.return_value = FakeResponse({"id": 81, "title": "T"})
    assert client.get_ticket(81) == {"id": 81, "title": "T"}
    mock_request.assert_called_once()
    request = mock_request.call_args[0]
    assert request[0] == "GET"
    assert request[1].endswith("/api/v1/tickets/81")


@patch("app.zammad.httpx.request")
def test_update_ticket_sends_json(mock_request):
    client = make_client()
    mock_request.return_value = FakeResponse({"id": 81})
    client.update_ticket(81, {"title": "new"})
    request = mock_request.call_args[0]
    assert request[0] == "PUT"
    assert mock_request.call_args.kwargs["json"] == {"title": "new"}


@patch("app.zammad.httpx.request")
def test_create_article(mock_request):
    client = make_client()
    mock_request.return_value = FakeResponse({"id": 9})
    client.create_article(81, {"type": "note"})
    request = mock_request.call_args[0]
    assert request[0] == "POST"
    assert "/articles" in request[1]


@patch("app.zammad.httpx.request")
def test_http_error_raises_zammad_error(mock_request):
    client = make_client()
    mock_request.return_value = FakeResponse("nope", status_code=500)
    with pytest.raises(ZammadError):
        client.get_ticket(81)


@patch("app.zammad.httpx.request")
def test_network_error_raises_zammad_error(mock_request):
    client = make_client()
    mock_request.side_effect = httpx.ConnectError("down")
    with pytest.raises(ZammadError):
        client.get_ticket(81)


@patch("app.zammad.httpx.get")
def test_get_attachment_returns_bytes(mock_get):
    client = make_client()
    mock_get.return_value = FakeResponse("binary audio")
    assert client.get_attachment("http://zammad.example.com/dl/audio.mp3") == b"binary audio"


@patch("app.zammad.httpx.request")
def test_get_ticket_articles(mock_request):
    client = make_client()
    mock_request.return_value = FakeResponse([{"id": 1}])
    assert client.get_ticket_articles(81) == [{"id": 1}]
    # endpoint Zammad correct : /api/v1/ticket_articles/by_ticket/<id>
    assert mock_request.call_args.args[1] == (
        "http://zammad.example.com/api/v1/ticket_articles/by_ticket/81"
    )


@patch("app.zammad.httpx.request")
def test_find_user_by_name_match(mock_request):
    client = make_client()
    mock_request.return_value = FakeResponse(
        [{"id": 7, "firstname": "Emily", "lastname": "Adams", "email": "e@e.com"}]
    )
    assert client.find_user_by_name("emily adams") == {
        "id": 7,
        "firstname": "Emily",
        "lastname": "Adams",
        "email": "e@e.com",
    }


@patch("app.zammad.httpx.request")
def test_find_user_by_name_no_match(mock_request):
    client = make_client()
    mock_request.return_value = FakeResponse(
        [{"id": 7, "firstname": "Jane", "lastname": "Doe", "email": "j@e.com"}]
    )
    assert client.find_user_by_name("emily adams") is None


@patch("app.zammad.httpx.request")
def test_find_user_by_name_zammad_error_returns_none(mock_request):
    client = make_client()
    mock_request.return_value = FakeResponse("nope", status_code=500)
    assert client.find_user_by_name("emily") is None


@patch("app.zammad.httpx.request")
def test_create_user(mock_request):
    client = make_client()
    mock_request.return_value = FakeResponse({"id": 42})
    assert client.create_user("Emily", "Adams") == {"id": 42}
    assert mock_request.call_args.kwargs["json"] == {"firstname": "Emily", "lastname": "Adams"}


@patch("app.zammad.httpx.request")
def test_create_user_with_email(mock_request):
    client = make_client()
    mock_request.return_value = FakeResponse({"id": 42})
    client.create_user("Emily", "Adams", email="e@e.com")
    assert mock_request.call_args.kwargs["json"] == {
        "firstname": "Emily",
        "lastname": "Adams",
        "email": "e@e.com",
    }


@patch("app.zammad.httpx.request")
def test_get_article(mock_request):
    client = make_client()
    mock_request.return_value = FakeResponse({"id": 104})
    assert client.get_article(81, 104) == {"id": 104}


@patch("app.zammad.httpx.request")
def test_find_ticket_by_number_found(mock_request):
    client = make_client()
    mock_request.return_value = FakeResponse(
        {"tickets": [{"id": 6475, "number": "202608069400166"}]}
    )
    result = client.find_ticket_by_number("202608069400166")
    assert result == {"id": 6475, "number": "202608069400166"}
    # la requête doit contenir number:<numéro>
    assert "number:202608069400166" in mock_request.call_args.args[1]


@patch("app.zammad.httpx.request")
def test_find_ticket_by_number_not_found(mock_request):
    client = make_client()
    mock_request.return_value = FakeResponse({"tickets": []})
    assert client.find_ticket_by_number("999") is None


@patch("app.zammad.httpx.request", side_effect=ZammadError("boom"))
def test_find_ticket_by_number_error_returns_none(mock_request):
    client = make_client()
    assert client.find_ticket_by_number("999") is None


def test_headers_include_token():
    client = make_client()
    headers = client._headers(accept_json=True)
    assert headers["Authorization"] == "Token token=t0k3n"
    assert headers["Accept"] == "application/json"
