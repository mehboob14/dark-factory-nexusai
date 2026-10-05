from __future__ import annotations

from httpapi import Probe, as_json, expect_error, fresh_key
from world import PASSWORD


LATER_PATHS = (
    "/authorizations",
    "/statement",
    "/correction-batches",
    "/split",
    "/signup",
    "/login",
)


def test_R157_no_browser_ui_or_testid_contract(probe: Probe, seed):
    for path in ("/", "/requests", "/split", "/signup", "/login"):
        html = probe.call("GET", path, headers={"Accept": "text/html"})
        text = html.text.lower()
        assert "data-testid" not in text, path
        if html.status_code == 200 and "text/html" in html.headers.get("content-type", "").lower():
            raise AssertionError(f"stage-1 must not serve HTML UI at {path}")


def test_R158_me_has_no_held_available_total_and_no_authorizations(probe: Probe, seed):
    token, _ = probe.login("src@acc.test", PASSWORD)
    me = probe.me(token)
    for leaked in ("available", "held", "total"):
        assert leaked not in me
    assert isinstance(me["balance"], int)
    unauth = probe.call("GET", "/authorizations")
    expect_error(unauth, 401, "unauthenticated")
    auth = probe.call("GET", "/authorizations", bearer=token)
    expect_error(auth, 404, "not_found")
    capture = probe.call(
        "POST",
        "/authorizations",
        body={"to_handle": "dstuser", "amount": 1},
        bearer=token,
        idem=fresh_key(),
    )
    expect_error(capture, 404, "not_found")
    pay = as_json(
        probe.call(
            "POST",
            "/payments",
            body={"to_handle": "dstuser", "amount": 1},
            bearer=token,
            idem=fresh_key(),
        )
    )
    for leaked in ("authorization_id", "refund_of", "payment_ids", "remaining_amount"):
        assert leaked not in pay
    listed = as_json(probe.call("GET", "/activity", bearer=token))["payments"][0]
    for leaked in ("authorization_id", "refund_of"):
        assert leaked not in listed


def test_R159_no_statements_corrections_refunds_or_as_of(probe: Probe, seed):
    token, _ = probe.login("src@acc.test", PASSWORD)
    me = as_json(probe.call("GET", "/me", bearer=token, query={"as_of": "2026-09-24T13:20:00+00:00"}))
    assert "as_of" not in me
    assert "known_at" not in me
    expect_error(probe.call("GET", "/statement", bearer=token), 404, "not_found")
    pay = as_json(
        probe.call(
            "POST",
            "/payments",
            body={"to_handle": "dstuser", "amount": 1},
            bearer=token,
            idem=fresh_key(),
        )
    )
    pid = pay["payment_id"]
    expect_error(
        probe.call(
            "POST",
            f"/payments/{pid}/corrections",
            body={"amount": 1},
            bearer=token,
            idem=fresh_key(),
        ),
        404,
        "not_found",
    )
    expect_error(
        probe.call(
            "POST",
            f"/payments/{pid}/refunds",
            body={"amount": 1},
            bearer=token,
            idem=fresh_key(),
        ),
        404,
        "not_found",
    )
    expect_error(
        probe.call(
            "POST",
            "/correction-batches",
            body={"corrections": []},
            bearer=token,
            idem=fresh_key(),
        ),
        404,
        "not_found",
    )


def test_R53_protected_later_paths_are_401_without_token(probe: Probe, seed):
    for path in ("/authorizations", "/statement", "/correction-batches"):
        resp = probe.call("GET", path)
        expect_error(resp, 401, "unauthenticated")
