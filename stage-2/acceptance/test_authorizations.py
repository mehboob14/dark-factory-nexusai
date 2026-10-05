"""Authorization API tests for Stage 2."""

from __future__ import annotations

from httpapi import Probe, as_json, expect_error, fresh_key, expect_stamp, expect_id
from world import PASSWORD


def test_get_me_includes_held_and_available(probe: Probe, seed):
    """GET /me returns balance, total, available, and held."""
    token, _ = probe.login("src@acc.test", PASSWORD)
    me = probe.me(token)

    assert me["balance"] == 10000
    assert me["total"] == 10000
    assert me["available"] == 10000
    assert me["held"] == 0


def test_post_authorizations_creates_hold(probe: Probe, seed):
    """POST /authorizations creates a hold and returns authorization."""
    payer, _ = probe.login("src@acc.test", PASSWORD)
    payee, _ = probe.login("dst@acc.test", PASSWORD)

    key = fresh_key()
    resp = probe.call(
        "POST",
        "/authorizations",
        body={
            "to_handle": "dstuser",
            "amount": 2000,
            "note": "test auth",
            "visibility": "public",
        },
        bearer=payer,
        idem=key,
    )
    assert resp.status_code == 201
    auth = as_json(resp)

    assert auth["authorization_id"]
    assert auth["from_user_id"] == "id_src"
    assert auth["to_user_id"] == "id_dst"
    assert auth["amount"] == 2000
    assert auth["status"] == "open"
    assert auth["captured_amount"] == 0
    assert auth["visibility"] == "public"
    expect_stamp(auth["expires_at"])
    expect_stamp(auth["created_at"])

    # Check that available is reduced
    me = probe.me(payer)
    assert me["total"] == 10000
    assert me["held"] == 2000
    assert me["available"] == 8000


def test_authorization_insufficient_available_funds(probe: Probe, seed):
    """POST /authorizations fails with 409 insufficient_funds if available is below amount."""
    token, _ = probe.login("src@acc.test", PASSWORD)

    # Create authorization that uses available
    key1 = fresh_key()
    resp1 = probe.call(
        "POST",
        "/authorizations",
        body={"to_handle": "dstuser", "amount": 9000},
        bearer=token,
        idem=key1,
    )
    assert resp1.status_code == 201

    # Try to create another that exceeds available
    key2 = fresh_key()
    resp2 = probe.call(
        "POST",
        "/authorizations",
        body={"to_handle": "dstuser", "amount": 2000},
        bearer=token,
        idem=key2,
    )
    expect_error(resp2, 409, "insufficient_funds")


def test_authorization_self_payment_rejected(probe: Probe, seed):
    """POST /authorizations rejects self-payment with 422 self_payment."""
    token, _ = probe.login("src@acc.test", PASSWORD)

    resp = probe.call(
        "POST",
        "/authorizations",
        body={"to_handle": "srcuser", "amount": 100},
        bearer=token,
        idem=fresh_key(),
    )
    expect_error(resp, 422, "self_payment")


def test_post_authorizations_idempotent(probe: Probe, seed):
    """POST /authorizations with same key returns same authorization."""
    token, _ = probe.login("src@acc.test", PASSWORD)
    key = fresh_key()

    resp1 = probe.call(
        "POST",
        "/authorizations",
        body={"to_handle": "dstuser", "amount": 1000},
        bearer=token,
        idem=key,
    )
    assert resp1.status_code == 201
    auth1 = as_json(resp1)

    resp2 = probe.call(
        "POST",
        "/authorizations",
        body={"to_handle": "dstuser", "amount": 1000},
        bearer=token,
        idem=key,
    )
    assert resp2.status_code == 201
    auth2 = as_json(resp2)

    assert auth1["authorization_id"] == auth2["authorization_id"]


def test_post_capture_captures_funds(probe: Probe, seed):
    """POST /authorizations/{id}/capture captures and releases remainder."""
    payer, _ = probe.login("src@acc.test", PASSWORD)
    payee, _ = probe.login("dst@acc.test", PASSWORD)

    # Create authorization
    auth_key = fresh_key()
    auth_resp = probe.call(
        "POST",
        "/authorizations",
        body={"to_handle": "dstuser", "amount": 2000},
        bearer=payer,
        idem=auth_key,
    )
    assert auth_resp.status_code == 201
    auth = as_json(auth_resp)

    # Capture partial amount
    cap_key = fresh_key()
    cap_resp = probe.call(
        "POST",
        f"/authorizations/{auth['authorization_id']}/capture",
        body={"amount": 1500},
        bearer=payee,
        idem=cap_key,
    )
    assert cap_resp.status_code == 201
    cap = as_json(cap_resp)

    assert cap["payment_id"]
    assert cap["authorization_id"] == auth["authorization_id"]
    assert cap["amount"] == 1500

    # Check payer's available increased (remainder released)
    payer_me = probe.me(payer)
    assert payer_me["held"] == 0  # All released after final capture
    assert payer_me["available"] == 9000  # 10000 - 1000 (final capture)


def test_post_void_releases_hold(probe: Probe, seed):
    """POST /authorizations/{id}/void releases hold without capturing."""
    payer, _ = probe.login("src@acc.test", PASSWORD)

    # Create authorization
    key = fresh_key()
    resp = probe.call(
        "POST",
        "/authorizations",
        body={"to_handle": "dstuser", "amount": 2000},
        bearer=payer,
        idem=key,
    )
    auth = as_json(resp)

    # Void it
    void_resp = probe.call(
        "POST",
        f"/authorizations/{auth['authorization_id']}/void",
        body={},
        bearer=payer,
    )
    assert void_resp.status_code == 200
    voided = as_json(void_resp)
    assert voided["status"] == "voided"

    # Check payer's held is zero
    me = probe.me(payer)
    assert me["held"] == 0
    assert me["available"] == 10000


def test_get_authorizations_lists_user_authorizations(probe: Probe, seed):
    """GET /authorizations returns authorizations for the user."""
    payer, _ = probe.login("src@acc.test", PASSWORD)
    payee, _ = probe.login("dst@acc.test", PASSWORD)

    # Create authorization
    key = fresh_key()
    auth_resp = probe.call(
        "POST",
        "/authorizations",
        body={"to_handle": "dstuser", "amount": 2000},
        bearer=payer,
        idem=key,
    )
    auth_id = as_json(auth_resp)["authorization_id"]

    # Get authorizations as payee
    resp = probe.call("GET", "/authorizations", bearer=payee)
    assert resp.status_code == 200
    body = as_json(resp)

    assert isinstance(body, dict)
    assert "authorizations" in body
    assert any(a["authorization_id"] == auth_id for a in body["authorizations"])


def test_authorization_ttl_from_fixture(probe: Probe, seed):
    """Authorization TTL is set from fixture's authorization_ttl_seconds."""
    token, _ = probe.login("src@acc.test", PASSWORD)

    resp = probe.call(
        "POST",
        "/authorizations",
        body={"to_handle": "dstuser", "amount": 1000},
        bearer=token,
        idem=fresh_key(),
    )
    auth = as_json(resp)

    # Check expires_at is created_at + 600 seconds
    expect_stamp(auth["created_at"])
    expect_stamp(auth["expires_at"])
