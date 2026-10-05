"""Concurrent correction tests for Stage 3."""

from __future__ import annotations

import threading

from httpapi import Probe, as_json, fresh_key, expect_error
from world import PASSWORD


def test_concurrent_corrections_same_revision_conflict(probe: Probe, seed):
    """Concurrent corrections on same expected_revision cannot both succeed."""
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

    results = []

    def correct_payment(amount, index):
        resp = probe.call(
            "POST",
            f"/payments/{payment_id}/corrections",
            body={
                "expected_revision": 1,
                "amount": amount,
                "effective_at": "2026-09-24T09:00:00+00:00",
                "reason": f"correction {index}",
            },
            bearer=payer,
            idem=fresh_key(),
        )
        results.append((index, resp.status_code))

    # Try to make two corrections on revision 1
    t1 = threading.Thread(target=correct_payment, args=(900, 1))
    t2 = threading.Thread(target=correct_payment, args=(800, 2))

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    # One should succeed, one should fail with stale_revision
    succeeded = sum(1 for _, status in results if status == 201)
    failed_stale = sum(1 for _, status in results if status == 409)

    assert succeeded == 1
    assert failed_stale == 1


def test_concurrent_corrections_different_revisions_succeed(probe: Probe, seed):
    """Concurrent corrections can succeed if on different revisions."""
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

    # Create first revision
    probe.call(
        "POST",
        f"/payments/{payment_id}/corrections",
        body={
            "expected_revision": 1,
            "amount": 900,
            "effective_at": "2026-09-24T09:00:00+00:00",
            "reason": "first",
        },
        bearer=payer,
        idem=fresh_key(),
    )

    # Create second revision
    probe.call(
        "POST",
        f"/payments/{payment_id}/corrections",
        body={
            "expected_revision": 2,
            "amount": 800,
            "effective_at": "2026-09-24T08:00:00+00:00",
            "reason": "second",
        },
        bearer=payer,
        idem=fresh_key(),
    )

    # Verify both revisions exist
    resp = probe.call("GET", f"/payments/{payment_id}/revisions", bearer=payer)
    revisions = as_json(resp)["revisions"]
    assert len(revisions) == 3  # Original + 2 corrections
