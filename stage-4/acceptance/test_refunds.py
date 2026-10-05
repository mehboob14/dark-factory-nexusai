"""Refund tests for Stage 4."""

from __future__ import annotations

from httpapi import Probe, as_json, expect_error, fresh_key
from world import PASSWORD


def test_post_refund_creates_reverse_payment(probe: Probe, seed):
    """POST /payments/{id}/refunds creates a new payment in opposite direction."""
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
    payment_id = as_json(pay_resp)["payment_id"]

    # Refund it
    ref_resp = probe.call(
        "POST",
        f"/payments/{payment_id}/refunds",
        body={"amount": 500},
        bearer=payee,
        idem=fresh_key(),
    )
    assert ref_resp.status_code == 201
    refund = as_json(ref_resp)

    assert refund["refund_of"] == payment_id
    assert refund["amount"] == 500
    assert refund["from_user_id"] == "id_dst"
    assert refund["to_user_id"] == "id_src"


def test_refund_forbidden_for_non_receiver(probe: Probe, seed):
    """Only the receiver can refund a payment."""
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

    # Try to refund as wrong user
    resp = probe.call(
        "POST",
        f"/payments/{payment_id}/refunds",
        body={"amount": 500},
        bearer=other,
        idem=fresh_key(),
    )
    expect_error(resp, 403, "forbidden")


def test_refund_exceeds_payment_rejected(probe: Probe, seed):
    """Refund amount cannot exceed payment amount."""
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
    payment_id = as_json(pay_resp)["payment_id"]

    # Try to refund more than payment
    resp = probe.call(
        "POST",
        f"/payments/{payment_id}/refunds",
        body={"amount": 1500},
        bearer=payee,
        idem=fresh_key(),
    )
    expect_error(resp, 422, "refund_exceeds_payment")


def test_multiple_partial_refunds(probe: Probe, seed):
    """Multiple partial refunds are allowed up to payment amount."""
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
    payment_id = as_json(pay_resp)["payment_id"]

    # Refund 400
    resp1 = probe.call(
        "POST",
        f"/payments/{payment_id}/refunds",
        body={"amount": 400},
        bearer=payee,
        idem=fresh_key(),
    )
    assert resp1.status_code == 201

    # Refund 300
    resp2 = probe.call(
        "POST",
        f"/payments/{payment_id}/refunds",
        body={"amount": 300},
        bearer=payee,
        idem=fresh_key(),
    )
    assert resp2.status_code == 201

    # Refund remaining 300
    resp3 = probe.call(
        "POST",
        f"/payments/{payment_id}/refunds",
        body={"amount": 300},
        bearer=payee,
        idem=fresh_key(),
    )
    assert resp3.status_code == 201

    # Try to refund more
    resp4 = probe.call(
        "POST",
        f"/payments/{payment_id}/refunds",
        body={"amount": 1},
        bearer=payee,
        idem=fresh_key(),
    )
    expect_error(resp4, 422, "refund_exceeds_payment")


def test_refund_idempotent(probe: Probe, seed):
    """Refunds with same idempotency key return same refund."""
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
    payment_id = as_json(pay_resp)["payment_id"]

    # Refund with a key
    key = fresh_key()
    resp1 = probe.call(
        "POST",
        f"/payments/{payment_id}/refunds",
        body={"amount": 500},
        bearer=payee,
        idem=key,
    )
    refund1 = as_json(resp1)

    # Refund again with same key
    resp2 = probe.call(
        "POST",
        f"/payments/{payment_id}/refunds",
        body={"amount": 500},
        bearer=payee,
        idem=key,
    )
    refund2 = as_json(resp2)

    assert refund1["payment_id"] == refund2["payment_id"]


def test_refund_of_refund_rejected(probe: Probe, seed):
    """Cannot refund a refund payment."""
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
    payment_id = as_json(pay_resp)["payment_id"]

    # Refund it
    ref_resp = probe.call(
        "POST",
        f"/payments/{payment_id}/refunds",
        body={"amount": 500},
        bearer=payee,
        idem=fresh_key(),
    )
    refund_id = as_json(ref_resp)["payment_id"]

    # Try to refund the refund (now payer is receiver of refund)
    resp = probe.call(
        "POST",
        f"/payments/{refund_id}/refunds",
        body={"amount": 200},
        bearer=payer,
        idem=fresh_key(),
    )
    expect_error(resp, 422, "invalid_refund_target")


def test_refund_moves_from_available_funds(probe: Probe, seed):
    """Refund is deducted from receiver's available funds."""
    payer, _ = probe.login("src@acc.test", PASSWORD)
    payee, _ = probe.login("dst@acc.test", PASSWORD)

    # Get payee's initial balance
    payee_me_before = probe.me(payee)

    # Make a payment
    pay_resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1000},
        bearer=payer,
        idem=fresh_key(),
    )
    payment_id = as_json(pay_resp)["payment_id"]

    # Check payee received it
    payee_me_received = probe.me(payee)
    assert payee_me_received["balance"] == payee_me_before["balance"] + 1000

    # Refund it
    probe.call(
        "POST",
        f"/payments/{payment_id}/refunds",
        body={"amount": 500},
        bearer=payee,
        idem=fresh_key(),
    )

    # Check payee's balance decreased
    payee_me_after = probe.me(payee)
    assert payee_me_after["balance"] == payee_me_received["balance"] - 500
