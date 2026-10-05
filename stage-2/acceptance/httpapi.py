"""Minimal HTTP helper for the acceptance suite.

Written for this suite. Not the harness client.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

import httpx

CONTROL_WAIT = 12.0
CALL_WAIT = 6.0

OFFSET_STAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?[+-]\d{2}:\d{2}$"
)


def fresh_key() -> str:
    return uuid.uuid4().hex


def as_json(resp: httpx.Response) -> Any:
    return resp.json()


def error_code(resp: httpx.Response) -> str:
    body = as_json(resp)
    err = body.get("error") if isinstance(body, dict) else None
    if not isinstance(err, dict):
        raise AssertionError(f"error object missing: {resp.status_code} {resp.text}")
    return str(err.get("code"))


class Probe:
    def __init__(self, origin: str):
        self.origin = origin.rstrip("/")
        self._client = httpx.Client(base_url=self.origin, timeout=CALL_WAIT)

    def close(self) -> None:
        self._client.close()

    def call(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        raw: bytes | str | None = None,
        bearer: str | None = None,
        idem: str | None | bool = False,
        query: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        wait: float | None = None,
    ) -> httpx.Response:
        hdrs: dict[str, str] = {}
        if bearer is not None:
            hdrs["Authorization"] = f"Bearer {bearer}"
        if idem is not False:
            if idem is None:
                hdrs["Idempotency-Key"] = ""
            else:
                hdrs["Idempotency-Key"] = str(idem)
        if body is not None or raw is not None:
            hdrs["Content-Type"] = "application/json; charset=utf-8"
        if headers:
            hdrs.update(headers)
        kwargs: dict[str, Any] = {"headers": hdrs, "params": query}
        if wait is not None:
            kwargs["timeout"] = wait
        if raw is not None:
            kwargs["content"] = raw
        elif body is not None:
            kwargs["json"] = body
        return self._client.request(method, path, **kwargs)

    def reset(self, fixture: dict[str, Any], *, expect_ok: bool = True) -> httpx.Response:
        resp = self.call("POST", "/_test/reset", body=fixture, wait=CONTROL_WAIT)
        if expect_ok:
            assert resp.status_code == 204, resp.text
            assert resp.content in (b"", b"null") or not resp.text.strip()
        return resp

    def login(self, email: str, password: str) -> tuple[str, dict[str, Any]]:
        resp = self.call("POST", "/auth/login", body={"email": email, "password": password})
        assert resp.status_code == 200, resp.text
        payload = as_json(resp)
        return payload["token"], payload

    def signup(self, email: str, password: str, display_name: str) -> tuple[str, dict[str, Any]]:
        resp = self.call(
            "POST",
            "/auth/signup",
            body={"email": email, "password": password, "display_name": display_name},
        )
        assert resp.status_code == 201, resp.text
        payload = as_json(resp)
        return payload["token"], payload

    def me(self, token: str) -> dict[str, Any]:
        resp = self.call("GET", "/me", bearer=token)
        assert resp.status_code == 200, resp.text
        return as_json(resp)

    def export(self) -> dict[str, Any]:
        resp = self.call("GET", "/_test/export", wait=CONTROL_WAIT)
        assert resp.status_code == 200, resp.text
        return as_json(resp)

    def import_state(self, snapshot: dict[str, Any], *, expect_ok: bool = True) -> httpx.Response:
        resp = self.call("POST", "/_test/import", body=snapshot, wait=CONTROL_WAIT)
        if expect_ok:
            assert resp.status_code == 204, resp.text
        return resp


def expect_error(resp: httpx.Response, status: int, code: str) -> None:
    assert resp.status_code == status, f"wanted {status} got {resp.status_code} {resp.text}"
    body = as_json(resp)
    assert isinstance(body, dict) and "error" in body, body
    err = body["error"]
    assert isinstance(err, dict), err
    assert err.get("code") == code, err
    assert "message" in err, err
    assert isinstance(err["message"], str)


def expect_json_type(resp: httpx.Response) -> None:
    ctype = resp.headers.get("content-type", "")
    assert ctype.lower().startswith("application/json"), ctype
    assert "charset=utf-8" in ctype.lower(), ctype


def expect_stamp(value: Any) -> None:
    assert isinstance(value, str), value
    assert OFFSET_STAMP.match(value), f"timestamp lacks numeric offset: {value!r}"


def expect_id(value: Any) -> None:
    assert isinstance(value, str) and 1 <= len(value) <= 64, value


def dumped(resp: httpx.Response) -> Any:
    return json.loads(resp.text)
