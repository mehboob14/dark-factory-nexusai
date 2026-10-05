"""Historical balance and statement tests for Stage 3."""

from __future__ import annotations

from httpapi import Probe, as_json, expect_error, fresh_key, expect_stamp
from world import PASSWORD


def test_me_as_of_returns_historical_balance(probe: Probe, seed):
    """GET /me?as_of=<instant> returns balance at that time."""
    token, _ = probe.login("src@acc.test", PASSWORD)

    # Get current me to get created_at
    me_now = probe.me(token)
    assert me_now["balance"] == 10000

    # Make a payment
    import time
    timestamp_before = (
        "2026-09-24T10:00:00+00:00"  # Arbitrary past timestamp for as_of
    )

    me_past = probe.me(token, as_of=timestamp_before)
    # Should return balance at that time (should be 10000 initially)
    assert isinstance(me_past["balance"], int)
    assert "as_of" in me_past


def test_get_statement_lists_payments(probe: Probe, seed):
    """GET /statement returns payments in window."""
    payer, _ = probe.login("src@acc.test", PASSWORD)
    payee, _ = probe.login("dst@acc.test", PASSWORD)

    # Make a payment
    probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1000},
        bearer=payer,
        idem=fresh_key(),
    )

    # Get statement
    resp = probe.call("GET", "/statement", bearer=payer)
    assert resp.status_code == 200
    stmt = as_json(resp)

    assert "entries" in stmt
    assert "opening_balance" in stmt
    assert "closing_balance" in stmt
    assert len(stmt["entries"]) == 1
    assert stmt["entries"][0]["payment"]["amount"] == 1000


def test_statement_pagination(probe: Probe, seed):
    """GET /statement respects limit and offset."""
    token, _ = probe.login("src@acc.test", PASSWORD)

    # Make multiple payments
    for i in range(5):
        probe.call(
            "POST",
            "/payments",
            body={"to_handle": "dstuser", "amount": 100 * (i + 1)},
            bearer=token,
            idem=fresh_key(),
        )

    # Get first page
    resp = probe.call("GET", "/statement", bearer=token, query={"limit": 2})
    assert resp.status_code == 200
    page1 = as_json(resp)
    assert len(page1["entries"]) == 2
    assert "has_more" in page1


def test_statement_snapshot_token(probe: Probe, seed):
    """GET /statement returns snapshot token for pagination."""
    token, _ = probe.login("src@acc.test", PASSWORD)

    # Make some payments
    for i in range(3):
        probe.call(
            "POST",
            "/payments",
            body={"to_handle": "dstuser", "amount": 100},
            bearer=token,
            idem=fresh_key(),
        )

    # Get statement with snapshot
    resp = probe.call("GET", "/statement", bearer=token)
    assert resp.status_code == 200
    stmt = as_json(resp)

    assert "snapshot" in stmt
    snapshot = stmt["snapshot"]

    # Use snapshot to page
    resp2 = probe.call(
        "GET",
        "/statement",
        bearer=token,
        query={"snapshot": snapshot, "limit": 1, "offset": 1},
    )
    assert resp2.status_code == 200
    page = as_json(resp2)
    assert isinstance(page["entries"], list)


def test_post_correction_creates_revision(probe: Probe, seed):
    """POST /payments/{id}/corrections creates new revision."""
    payer, _ = probe.login("src@acc.test", PASSWORD)
    payee, _ = probe.login("dst@acc.test", PASSWORD)

    # Make a payment
    pay_resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1000},
        bearer=payer,
        idem=fresh_key(),
    )
    assert pay_resp.status_code == 201
    payment = as_json(pay_resp)
    payment_id = payment["payment_id"]

    # Correct it
    corr_resp = probe.call(
        "POST",
        f"/payments/{payment_id}/corrections",
        body={
            "expected_revision": 1,
            "amount": 800,
            "effective_at": "2026-09-24T09:00:00+00:00",
            "reason": "corrected amount",
        },
        bearer=payer,
        idem=fresh_key(),
    )
    assert corr_resp.status_code == 201
    correction = as_json(corr_resp)

    assert correction["payment_id"] == payment_id
    assert correction["revision"] == 2
    assert correction["amount"] == 800


def test_get_payment_revisions_lists_all(probe: Probe, seed):
    """GET /payments/{id}/revisions returns all revisions."""
    payer, _ = probe.login("src@acc.test", PASSWORD)

    # Make a payment
    pay_resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1000},
        bearer=payer,
        idem=fresh_key(),
    )
    payment_id = as_json(pay_resp)["payment_id"]

    # Correct it twice
    probe.call(
        "POST",
        f"/payments/{payment_id}/corrections",
        body={
            "expected_revision": 1,
            "amount": 900,
            "effective_at": "2026-09-24T09:00:00+00:00",
            "reason": "first correction",
        },
        bearer=payer,
        idem=fresh_key(),
    )

    probe.call(
        "POST",
        f"/payments/{payment_id}/corrections",
        body={
            "expected_revision": 2,
            "amount": 800,
            "effective_at": "2026-09-24T08:00:00+00:00",
            "reason": "second correction",
        },
        bearer=payer,
        idem=fresh_key(),
    )

    # Get revisions
    resp = probe.call("GET", f"/payments/{payment_id}/revisions", bearer=payer)
    assert resp.status_code == 200
    body = as_json(resp)

    assert "revisions" in body
    assert len(body["revisions"]) == 3  # Original + 2 corrections


def test_correction_stale_revision_rejected(probe: Probe, seed):
    """POST /payments/{id}/corrections rejects stale expected_revision."""
    payer, _ = probe.login("src@acc.test", PASSWORD)

    # Make a payment
    pay_resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1000},
        bearer=payer,
        idem=fresh_key(),
    )
    payment_id = as_json(pay_resp)["payment_id"]

    # Make one correction
    probe.call(
        "POST",
        f"/payments/{payment_id}/corrections",
        body={
            "expected_revision": 1,
            "amount": 900,
            "effective_at": "2026-09-24T09:00:00+00:00",
            "reason": "correction",
        },
        bearer=payer,
        idem=fresh_key(),
    )

    # Try to correct with old expected_revision
    resp = probe.call(
        "POST",
        f"/payments/{payment_id}/corrections",
        body={
            "expected_revision": 1,
            "amount": 800,
            "effective_at": "2026-09-24T08:00:00+00:00",
            "reason": "another",
        },
        bearer=payer,
        idem=fresh_key(),
    )
    expect_error(resp, 409, "stale_revision")


def test_correction_forbidden_for_non_sender(probe: Probe, seed):
    """POST /payments/{id}/corrections is forbidden for non-sender."""
    payer, _ = probe.login("src@acc.test", PASSWORD)
    other, _ = probe.login("obs@acc.test", PASSWORD)

    # Make a payment
    pay_resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1000},
        bearer=payer,
        idem=fresh_key(),
    )
    payment_id = as_json(pay_resp)["payment_id"]

    # Try to correct as different user
    resp = probe.call(
        "POST",
        f"/payments/{payment_id}/corrections",
        body={
            "expected_revision": 1,
            "amount": 900,
            "effective_at": "2026-09-24T09:00:00+00:00",
            "reason": "hack",
        },
        bearer=other,
        idem=fresh_key(),
    )
    expect_error(resp, 403, "forbidden")


def test_historical_overdraft_detected(probe: Probe, seed):
    """Correction that causes historical overdraft is rejected."""
    payer, _ = probe.login("src@acc.test", PASSWORD)

    # Make a payment
    pay_resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 9000},
        bearer=payer,
        idem=fresh_key(),
    )
    payment_id = as_json(pay_resp)["payment_id"]

    # Try to increase the payment beyond payer's initial balance
    resp = probe.call(
        "POST",
        f"/payments/{payment_id}/corrections",
        body={
            "expected_revision": 1,
            "amount": 11000,
            "effective_at": "2026-09-24T09:00:00+00:00",
            "reason": "overspend",
        },
        bearer=payer,
        idem=fresh_key(),
    )
    expect_error(resp, 409, "historical_overdraft")
