"""Export and import tests for Stage 2."""

from __future__ import annotations

from httpapi import Probe, as_json, fresh_key
from world import PASSWORD


def test_export_includes_authorizations(probe: Probe, seed):
    """_test/export includes authorizations array."""
    token, _ = probe.login("src@acc.test", PASSWORD)

    # Create an authorization
    probe.call(
        "POST",
        "/authorizations",
        body={"to_handle": "dstuser", "amount": 1000},
        bearer=token,
        idem=fresh_key(),
    )

    # Export
    exported = probe.export()

    assert "authorizations" in exported
    assert isinstance(exported["authorizations"], list)
    assert len(exported["authorizations"]) == 1


def test_import_restores_authorizations(probe: Probe, seed):
    """Import from stage-1 service accepts authorizations."""
    token, _ = probe.login("src@acc.test", PASSWORD)

    # Export current state
    before = probe.export()

    # Create authorization
    probe.call(
        "POST",
        "/authorizations",
        body={"to_handle": "dstuser", "amount": 2000},
        bearer=token,
        idem=fresh_key(),
    )

    # Export with authorization
    after = probe.export()
    assert len(after["authorizations"]) == 1

    # Re-import the state with authorization
    import_resp = probe.import_state(after)
    assert import_resp.status_code == 204

    # Verify authorization is still there
    me = probe.me(token)
    assert me["held"] == 2000
    assert me["available"] == 8000


def test_import_preserves_session(probe: Probe, seed):
    """Browser session remains valid after import."""
    token, _ = probe.login("src@acc.test", PASSWORD)

    # Verify user is logged in
    me1 = probe.me(token)
    assert me1["handle"] == "srcuser"

    # Export and import
    state = probe.export()
    probe.import_state(state)

    # Token should still work
    me2 = probe.me(token)
    assert me2["handle"] == "srcuser"
    assert me2["balance"] == me1["balance"]


def test_import_preserves_pending_retry(probe: Probe, seed):
    """Import preserves retry state for payments with lost responses."""
    payer, _ = probe.login("src@acc.test", PASSWORD)

    # Create a payment
    key = fresh_key()
    resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 500},
        bearer=payer,
        idem=key,
    )
    assert resp.status_code == 201

    # Export
    exported = probe.export()

    # Import
    probe.import_state(exported)

    # Retry with same key and body should succeed
    retry_resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 500},
        bearer=payer,
        idem=key,
    )
    assert retry_resp.status_code == 200

    # Balance should not change
    me = probe.me(payer)
    assert me["balance"] == 9500  # 10000 - 500
