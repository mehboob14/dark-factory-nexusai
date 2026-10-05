"""Batch correction tests for Stage 4."""

from __future__ import annotations

from httpapi import Probe, as_json, expect_error, fresh_key
from world import PASSWORD


def test_post_correction_batch_corrects_multiple(probe: Probe, seed):
    """POST /correction-batches corrects multiple payments atomically."""
    operator, _ = probe.login("op@acc.test", PASSWORD)
    user1, _ = probe.login("src@acc.test", PASSWORD)
    user2, _ = probe.login("dst@acc.test", PASSWORD)

    # Create two payments
    pay1_resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1000},
        bearer=user1,
        idem=fresh_key(),
    )
    pay1_id = as_json(pay1_resp)["payment_id"]

    pay2_resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "obsuser", "amount": 500},
        bearer=user2,
        idem=fresh_key(),
    )
    pay2_id = as_json(pay2_resp)["payment_id"]

    # Batch correct them
    batch_resp = probe.call(
        "POST",
        "/correction-batches",
        body={
            "corrections": [
                {
                    "payment_id": pay1_id,
                    "expected_revision": 1,
                    "amount": 900,
                    "effective_at": "2026-09-24T09:00:00+00:00",
                    "reason": "batch correction 1",
                },
                {
                    "payment_id": pay2_id,
                    "expected_revision": 1,
                    "amount": 400,
                    "effective_at": "2026-09-24T09:00:00+00:00",
                    "reason": "batch correction 2",
                },
            ]
        },
        bearer=operator,
        idem=fresh_key(),
    )
    assert batch_resp.status_code == 201
    batch = as_json(batch_resp)

    assert batch["correction_batch_id"]
    assert len(batch["revisions"]) == 2


def test_batch_correction_requires_operator(probe: Probe, seed):
    """Only settlement operator can create correction batches."""
    non_operator, _ = probe.login("src@acc.test", PASSWORD)

    pay_resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1000},
        bearer=non_operator,
        idem=fresh_key(),
    )
    payment_id = as_json(pay_resp)["payment_id"]

    # Try to batch correct as non-operator
    resp = probe.call(
        "POST",
        "/correction-batches",
        body={
            "corrections": [
                {
                    "payment_id": payment_id,
                    "expected_revision": 1,
                    "amount": 900,
                    "effective_at": "2026-09-24T09:00:00+00:00",
                    "reason": "unauthorized",
                }
            ]
        },
        bearer=non_operator,
        idem=fresh_key(),
    )
    expect_error(resp, 403, "forbidden")


def test_batch_correction_empty_list_rejected(probe: Probe, seed):
    """Batch correction requires 1-32 items."""
    operator, _ = probe.login("op@acc.test", PASSWORD)

    resp = probe.call(
        "POST",
        "/correction-batches",
        body={"corrections": []},
        bearer=operator,
        idem=fresh_key(),
    )
    expect_error(resp, 422, "validation_failed")


def test_batch_correction_atomic_on_failure(probe: Probe, seed):
    """Batch correction fails atomically if any item fails."""
    operator, _ = probe.login("op@acc.test", PASSWORD)
    user, _ = probe.login("src@acc.test", PASSWORD)

    # Create two payments
    pay1_resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1000},
        bearer=user,
        idem=fresh_key(),
    )
    pay1_id = as_json(pay1_resp)["payment_id"]

    pay2_resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "obsuser", "amount": 500},
        bearer=user,
        idem=fresh_key(),
    )
    pay2_id = as_json(pay2_resp)["payment_id"]

    # Try to batch correct with one stale revision
    resp = probe.call(
        "POST",
        "/correction-batches",
        body={
            "corrections": [
                {
                    "payment_id": pay1_id,
                    "expected_revision": 1,
                    "amount": 900,
                    "effective_at": "2026-09-24T09:00:00+00:00",
                    "reason": "ok",
                },
                {
                    "payment_id": pay2_id,
                    "expected_revision": 999,  # Wrong revision
                    "amount": 400,
                    "effective_at": "2026-09-24T09:00:00+00:00",
                    "reason": "fail",
                },
            ]
        },
        bearer=operator,
        idem=fresh_key(),
    )
    expect_error(resp, 409, "stale_revision")

    # Both payments should still be uncorrected
    pay1_revs = probe.call("GET", f"/payments/{pay1_id}/revisions", bearer=user)
    assert len(as_json(pay1_revs)["revisions"]) == 1  # Only original


def test_batch_correction_duplicate_payment_ids_rejected(probe: Probe, seed):
    """Batch correction rejects duplicate payment IDs."""
    operator, _ = probe.login("op@acc.test", PASSWORD)
    user, _ = probe.login("src@acc.test", PASSWORD)

    pay_resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1000},
        bearer=user,
        idem=fresh_key(),
    )
    payment_id = as_json(pay_resp)["payment_id"]

    # Try to correct same payment twice
    resp = probe.call(
        "POST",
        "/correction-batches",
        body={
            "corrections": [
                {
                    "payment_id": payment_id,
                    "expected_revision": 1,
                    "amount": 900,
                    "effective_at": "2026-09-24T09:00:00+00:00",
                    "reason": "first",
                },
                {
                    "payment_id": payment_id,
                    "expected_revision": 1,
                    "amount": 800,
                    "effective_at": "2026-09-24T09:00:00+00:00",
                    "reason": "duplicate",
                },
            ]
        },
        bearer=operator,
        idem=fresh_key(),
    )
    expect_error(resp, 422, "validation_failed")


def test_batch_correction_idempotent(probe: Probe, seed):
    """Batch corrections with same key return same batch ID."""
    operator, _ = probe.login("op@acc.test", PASSWORD)
    user, _ = probe.login("src@acc.test", PASSWORD)

    pay_resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1000},
        bearer=user,
        idem=fresh_key(),
    )
    payment_id = as_json(pay_resp)["payment_id"]

    key = fresh_key()
    batch_body = {
        "corrections": [
            {
                "payment_id": payment_id,
                "expected_revision": 1,
                "amount": 900,
                "effective_at": "2026-09-24T09:00:00+00:00",
                "reason": "batch",
            }
        ]
    }

    # First batch
    resp1 = probe.call(
        "POST",
        "/correction-batches",
        body=batch_body,
        bearer=operator,
        idem=key,
    )
    batch1 = as_json(resp1)

    # Retry with same key
    resp2 = probe.call(
        "POST",
        "/correction-batches",
        body=batch_body,
        bearer=operator,
        idem=key,
    )
    batch2 = as_json(resp2)

    assert batch1["correction_batch_id"] == batch2["correction_batch_id"]
