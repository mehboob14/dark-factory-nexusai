from __future__ import annotations

from httpapi import Probe, as_json, expect_error, expect_id, expect_stamp, fresh_key
from world import PASSWORD


def _src(probe: Probe) -> str:
    return probe.login("src@acc.test", PASSWORD)[0]


def test_R69_payment_defaults_and_required_fields(probe: Probe, seed):
    token = _src(probe)
    missing = probe.call("POST", "/payments", body={"amount": 1}, bearer=token, idem=fresh_key())
    expect_error(missing, 422, "validation_failed")
    missing_amt = probe.call(
        "POST", "/payments", body={"to_handle": "dstuser"}, bearer=token, idem=fresh_key()
    )
    expect_error(missing_amt, 422, "validation_failed")
    ok = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 5},
        bearer=token,
        idem=fresh_key(),
    )
    assert ok.status_code == 201
    body = as_json(ok)
    assert body["note"] == ""
    assert body["visibility"] == "public"


def test_R70_payment_success_shape(probe: Probe, seed):
    token = _src(probe)
    resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 6, "note": "n", "visibility": "private"},
        bearer=token,
        idem=fresh_key(),
    )
    assert resp.status_code == 201
    body = as_json(resp)
    for key in (
        "payment_id",
        "from_user_id",
        "from_handle",
        "to_user_id",
        "to_handle",
        "amount",
        "currency",
        "note",
        "visibility",
        "request_id",
        "created_at",
    ):
        assert key in body
    assert body["from_user_id"] == "id_src"
    assert body["from_handle"] == "srcuser"
    assert body["to_user_id"] == "id_dst"
    assert body["to_handle"] == "dstuser"
    assert body["amount"] == 6
    assert body["currency"] == "EUR"
    assert body["note"] == "n"
    assert body["visibility"] == "private"
    assert body["request_id"] is None
    expect_id(body["payment_id"])
    expect_stamp(body["created_at"])


def test_R71_settlement_id_null_on_direct_payment(probe: Probe, seed):
    token = _src(probe)
    resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1},
        bearer=token,
        idem=fresh_key(),
    )
    assert resp.status_code == 201
    body = as_json(resp)
    assert "settlement_id" in body
    assert body["settlement_id"] is None


def test_R72_insufficient_funds_moves_nothing(probe: Probe, seed):
    src = _src(probe)
    dst, _ = probe.login("dst@acc.test", PASSWORD)
    before_s = probe.me(src)["balance"]
    before_d = probe.me(dst)["balance"]
    resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": before_s + 1},
        bearer=src,
        idem=fresh_key(),
    )
    expect_error(resp, 409, "insufficient_funds")
    assert probe.me(src)["balance"] == before_s
    assert probe.me(dst)["balance"] == before_d
    feed = as_json(probe.call("GET", "/activity", bearer=src))
    assert feed["payments"] == []


def test_R73_amount_boundaries(probe: Probe, seed):
    token = _src(probe)
    for amount in (0, -1, 1_000_000_001, 1.5):
        resp = probe.call(
            "POST",
            "/payments",
            body={"to_handle": "dstuser", "amount": amount},
            bearer=token,
            idem=fresh_key(),
        )
        expect_error(resp, 422, "validation_failed")
    one = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1},
        bearer=token,
        idem=fresh_key(),
    )
    assert one.status_code == 201


def test_R74_self_payment_is_422(probe: Probe, seed):
    token = _src(probe)
    resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "srcuser", "amount": 1},
        bearer=token,
        idem=fresh_key(),
    )
    expect_error(resp, 422, "self_payment")


def test_R75_note_max_200_code_points(probe: Probe, seed):
    token = _src(probe)
    ok = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1, "note": "é" * 200},
        bearer=token,
        idem=fresh_key(),
    )
    assert ok.status_code == 201
    assert as_json(ok)["note"] == "é" * 200
    bad = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1, "note": "é" * 201},
        bearer=token,
        idem=fresh_key(),
    )
    expect_error(bad, 422, "validation_failed")


def test_R76_visibility_must_be_public_or_private(probe: Probe, seed):
    token = _src(probe)
    resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1, "visibility": "PUBLIC"},
        bearer=token,
        idem=fresh_key(),
    )
    expect_error(resp, 422, "validation_failed")


def test_R77_unknown_handle_is_404(probe: Probe, seed):
    token = _src(probe)
    resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "nobodyhere", "amount": 1},
        bearer=token,
        idem=fresh_key(),
    )
    expect_error(resp, 404, "not_found")


def test_R78_debit_and_credit_are_atomic(probe: Probe, seed, total):
    src = _src(probe)
    dst, _ = probe.login("dst@acc.test", PASSWORD)
    before_s = probe.me(src)["balance"]
    before_d = probe.me(dst)["balance"]
    resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 40},
        bearer=src,
        idem=fresh_key(),
    )
    assert resp.status_code == 201
    assert probe.me(src)["balance"] == before_s - 40
    assert probe.me(dst)["balance"] == before_d + 40
    seen = 0
    for email in (
        "src@acc.test",
        "dst@acc.test",
        "op@acc.test",
        "obs@acc.test",
        "p0@acc.test",
        "p1@acc.test",
        "p2@acc.test",
        "p3@acc.test",
        "p4@acc.test",
    ):
        tok, _ = probe.login(email, PASSWORD)
        seen += probe.me(tok)["balance"]
    assert seen == total


def test_R79_note_is_verbatim_including_emoji(probe: Probe, seed):
    token = _src(probe)
    note = "  hi\t💰\n"
    resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1, "note": note},
        bearer=token,
        idem=fresh_key(),
    )
    assert resp.status_code == 201
    assert as_json(resp)["note"] == note
    feed = as_json(probe.call("GET", "/activity", bearer=token))
    assert feed["payments"][0]["note"] == note
