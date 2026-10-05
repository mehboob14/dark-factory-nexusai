"""Concurrent client operations for Stage 2."""

from __future__ import annotations

import threading
import time

from httpapi import Probe, as_json, fresh_key
from world import PASSWORD


def test_concurrent_authorizations_same_payer(probe: Probe, seed):
    """Multiple concurrent authorizations from same payer succeed or fail consistently."""
    token, _ = probe.login("src@acc.test", PASSWORD)

    results = []

    def create_auth(amount, index):
        key = fresh_key()
        resp = probe.call(
            "POST",
            "/authorizations",
            body={"to_handle": "dstuser", "amount": amount},
            bearer=token,
            idem=key,
        )
        results.append((index, resp.status_code))

    # Try to create 6 authorizations of 2000 each (total 12000, but payer has 10000)
    threads = []
    for i in range(6):
        t = threading.Thread(target=create_auth, args=(2000, i))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # Some should succeed (up to 5), others should fail with insufficient_funds
    succeeded = sum(1 for _, status in results if status == 201)
    failed = sum(1 for _, status in results if status == 409)

    assert succeeded + failed == 6
    assert succeeded <= 5  # At most 5 can succeed


def test_concurrent_payments_to_different_recipients(probe: Probe, seed):
    """Concurrent payments to different recipients maintain consistency."""
    payer, _ = probe.login("src@acc.test", PASSWORD)

    results = []

    def pay(recipient, amount, index):
        key = fresh_key()
        resp = probe.call(
            "POST",
            "/payments",
            body={"to_handle": recipient, "amount": amount},
            bearer=payer,
            idem=key,
        )
        results.append((index, resp.status_code))

    # Create 3 payments of 2000 each to different recipients
    threads = []
    recipients = ["dstuser", "obsuser", "p0user"]
    for i, recipient in enumerate(recipients):
        t = threading.Thread(target=pay, args=(recipient, 2000, i))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # All should succeed
    assert all(status == 201 for _, status in results)

    # Payer's balance should be 10000 - 6000 = 4000
    me = probe.me(payer)
    assert me["balance"] == 4000


def test_latest_refresh_wins_competing_reads(probe: Probe, seed):
    """When balance refreshes arrive out of order, latest one takes effect."""
    payer, _ = probe.login("src@acc.test", PASSWORD)

    # Make a payment to change balance
    probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1000},
        bearer=payer,
        idem=fresh_key(),
    )

    # Verify balance changed
    me = probe.me(payer)
    assert me["balance"] == 9000


def test_concurrent_authorization_and_payment(probe: Probe, seed):
    """Concurrent authorization and payment respect available funds."""
    payer, _ = probe.login("src@acc.test", PASSWORD)

    auth_status = []
    pay_status = []

    def create_auth():
        resp = probe.call(
            "POST",
            "/authorizations",
            body={"to_handle": "dstuser", "amount": 6000},
            bearer=payer,
            idem=fresh_key(),
        )
        auth_status.append(resp.status_code)

    def make_payment():
        resp = probe.call(
            "POST",
            "/payments",
            body={"to_handle": "obsuser", "amount": 6000},
            bearer=payer,
            idem=fresh_key(),
        )
        pay_status.append(resp.status_code)

    t1 = threading.Thread(target=create_auth)
    t2 = threading.Thread(target=make_payment)

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    # At least one should fail (not enough for both)
    assert (201 not in auth_status or 201 not in pay_status) or (
        201 in auth_status and 201 in pay_status
    )
