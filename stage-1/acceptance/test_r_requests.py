from __future__ import annotations

from httpapi import Probe, as_json, expect_error, expect_id, expect_stamp, fresh_key
from world import PASSWORD


def _pair(probe: Probe):
    return probe.login("src@acc.test", PASSWORD)[0], probe.login("dst@acc.test", PASSWORD)[0]


def test_R80_create_request_defaults(probe: Probe, seed):
    src, dst = _pair(probe)
    missing = probe.call("POST", "/requests", body={"amount": 1}, bearer=dst, idem=fresh_key())
    expect_error(missing, 422, "validation_failed")
    ok = probe.call(
        "POST",
        "/requests",
        body={"payer_handle": "srcuser", "amount": 12},
        bearer=dst,
        idem=fresh_key(),
    )
    assert ok.status_code == 201
    assert as_json(ok)["note"] == ""


def test_R81_request_success_shape(probe: Probe, seed):
    src, dst = _pair(probe)
    resp = probe.call(
        "POST",
        "/requests",
        body={"payer_handle": "srcuser", "amount": 12, "note": "ask"},
        bearer=dst,
        idem=fresh_key(),
    )
    assert resp.status_code == 201
    body = as_json(resp)
    assert body["requester_id"] == "id_dst"
    assert body["requester_handle"] == "dstuser"
    assert body["payer_id"] == "id_src"
    assert body["payer_handle"] == "srcuser"
    assert body["amount"] == 12
    assert body["currency"] == "EUR"
    assert body["note"] == "ask"
    assert body["status"] == "pending"
    assert body["payment_id"] is None
    expect_id(body["request_id"])
    expect_stamp(body["created_at"])


def test_R82_request_amount_boundaries(probe: Probe, seed):
    _, dst = _pair(probe)
    for amount in (0, 1_000_000_001, 2.2):
        expect_error(
            probe.call(
                "POST",
                "/requests",
                body={"payer_handle": "srcuser", "amount": amount},
                bearer=dst,
                idem=fresh_key(),
            ),
            422,
            "validation_failed",
        )


def test_R83_self_request_is_422(probe: Probe, seed):
    src, _ = _pair(probe)
    expect_error(
        probe.call(
            "POST",
            "/requests",
            body={"payer_handle": "srcuser", "amount": 1},
            bearer=src,
            idem=fresh_key(),
        ),
        422,
        "self_request",
    )


def test_R84_request_note_too_long(probe: Probe, seed):
    _, dst = _pair(probe)
    expect_error(
        probe.call(
            "POST",
            "/requests",
            body={"payer_handle": "srcuser", "amount": 1, "note": "n" * 201},
            bearer=dst,
            idem=fresh_key(),
        ),
        422,
        "validation_failed",
    )


def test_R85_unknown_payer_handle(probe: Probe, seed):
    _, dst = _pair(probe)
    expect_error(
        probe.call(
            "POST",
            "/requests",
            body={"payer_handle": "nopeuser", "amount": 1},
            bearer=dst,
            idem=fresh_key(),
        ),
        404,
        "not_found",
    )


def test_R86_request_may_exceed_payer_balance(probe: Probe, seed):
    src, dst = _pair(probe)
    amount = probe.me(src)["balance"] + 50
    resp = probe.call(
        "POST",
        "/requests",
        body={"payer_handle": "srcuser", "amount": amount},
        bearer=dst,
        idem=fresh_key(),
    )
    assert resp.status_code == 201
    assert as_json(resp)["status"] == "pending"


def test_R87_request_has_one_terminal_status(probe: Probe, seed):
    src, dst = _pair(probe)
    created = as_json(
        probe.call(
            "POST",
            "/requests",
            body={"payer_handle": "srcuser", "amount": 1},
            bearer=dst,
            idem=fresh_key(),
        )
    )
    rid = created["request_id"]
    paid = probe.call("POST", f"/requests/{rid}/pay", body={}, bearer=src, idem=fresh_key())
    assert paid.status_code == 201
    listed = as_json(probe.call("GET", "/requests", bearer=src, query={"status": "paid"}))
    assert any(r["request_id"] == rid and r["status"] == "paid" for r in listed["requests"])


def test_R88_only_payer_pays_with_optional_visibility(probe: Probe, seed):
    src, dst = _pair(probe)
    rid = as_json(
        probe.call(
            "POST",
            "/requests",
            body={"payer_handle": "srcuser", "amount": 3},
            bearer=dst,
            idem=fresh_key(),
        )
    )["request_id"]
    pay = probe.call(
        "POST",
        f"/requests/{rid}/pay",
        body={"visibility": "private"},
        bearer=src,
        idem=fresh_key(),
    )
    assert pay.status_code == 201
    assert as_json(pay)["visibility"] == "private"
    assert as_json(pay)["request_id"] == rid


def test_R89_empty_body_and_explicit_public_are_different(probe: Probe, seed):
    src, dst = _pair(probe)
    rid = as_json(
        probe.call(
            "POST",
            "/requests",
            body={"payer_handle": "srcuser", "amount": 2},
            bearer=dst,
            idem=fresh_key(),
        )
    )["request_id"]
    key = fresh_key()
    first = probe.call("POST", f"/requests/{rid}/pay", body={}, bearer=src, idem=key)
    assert first.status_code == 201
    reuse = probe.call(
        "POST",
        f"/requests/{rid}/pay",
        body={"visibility": "public"},
        bearer=src,
        idem=key,
    )
    expect_error(reuse, 409, "idempotency_key_reuse")


def test_R90_pay_returns_payment_and_marks_request_paid(probe: Probe, seed):
    src, dst = _pair(probe)
    rid = as_json(
        probe.call(
            "POST",
            "/requests",
            body={"payer_handle": "srcuser", "amount": 8},
            bearer=dst,
            idem=fresh_key(),
        )
    )["request_id"]
    pay = as_json(probe.call("POST", f"/requests/{rid}/pay", body={}, bearer=src, idem=fresh_key()))
    assert pay["request_id"] == rid
    assert pay["amount"] == 8
    assert pay["settlement_id"] is None
    listed = as_json(probe.call("GET", "/requests", bearer=dst))
    item = next(r for r in listed["requests"] if r["request_id"] == rid)
    assert item["status"] == "paid"
    assert item["payment_id"] == pay["payment_id"]


def test_R91_pay_non_pending_is_409(probe: Probe, seed):
    src, dst = _pair(probe)
    rid = as_json(
        probe.call(
            "POST",
            "/requests",
            body={"payer_handle": "srcuser", "amount": 1},
            bearer=dst,
            idem=fresh_key(),
        )
    )["request_id"]
    probe.call("POST", f"/requests/{rid}/decline", body={}, bearer=src)
    expect_error(
        probe.call("POST", f"/requests/{rid}/pay", body={}, bearer=src, idem=fresh_key()),
        409,
        "request_not_pending",
    )


def test_R92_pay_short_is_insufficient_funds_and_stays_pending(probe: Probe, seed):
    src, dst = _pair(probe)
    amount = probe.me(src)["balance"] + 5
    rid = as_json(
        probe.call(
            "POST",
            "/requests",
            body={"payer_handle": "srcuser", "amount": amount},
            bearer=dst,
            idem=fresh_key(),
        )
    )["request_id"]
    expect_error(
        probe.call("POST", f"/requests/{rid}/pay", body={}, bearer=src, idem=fresh_key()),
        409,
        "insufficient_funds",
    )
    listed = as_json(probe.call("GET", "/requests", bearer=src))
    item = next(r for r in listed["requests"] if r["request_id"] == rid)
    assert item["status"] == "pending"
    assert item["payment_id"] is None


def test_R93_non_payer_pay_is_403(probe: Probe, seed):
    src, dst = _pair(probe)
    obs, _ = probe.login("obs@acc.test", PASSWORD)
    rid = as_json(
        probe.call(
            "POST",
            "/requests",
            body={"payer_handle": "srcuser", "amount": 1},
            bearer=dst,
            idem=fresh_key(),
        )
    )["request_id"]
    expect_error(
        probe.call("POST", f"/requests/{rid}/pay", body={}, bearer=obs, idem=fresh_key()),
        403,
        "forbidden",
    )
    expect_error(
        probe.call("POST", f"/requests/{rid}/pay", body={}, bearer=dst, idem=fresh_key()),
        403,
        "forbidden",
    )


def test_R94_unknown_request_is_404(probe: Probe, seed):
    src, _ = _pair(probe)
    expect_error(
        probe.call("POST", "/requests/does-not-exist/pay", body={}, bearer=src, idem=fresh_key()),
        404,
        "not_found",
    )


def test_R95_replay_pay_after_paid_returns_original(probe: Probe, seed):
    src, dst = _pair(probe)
    rid = as_json(
        probe.call(
            "POST",
            "/requests",
            body={"payer_handle": "srcuser", "amount": 4},
            bearer=dst,
            idem=fresh_key(),
        )
    )["request_id"]
    key = fresh_key()
    first = probe.call("POST", f"/requests/{rid}/pay", body={}, bearer=src, idem=key)
    assert first.status_code == 201
    before = probe.me(src)["balance"]
    replay = probe.call("POST", f"/requests/{rid}/pay", body={}, bearer=src, idem=key)
    assert replay.status_code == 200
    assert as_json(replay) == as_json(first)
    assert probe.me(src)["balance"] == before


def test_R96_decline_rules(probe: Probe, seed):
    src, dst = _pair(probe)
    obs, _ = probe.login("obs@acc.test", PASSWORD)
    rid = as_json(
        probe.call(
            "POST",
            "/requests",
            body={"payer_handle": "srcuser", "amount": 1},
            bearer=dst,
            idem=fresh_key(),
        )
    )["request_id"]
    expect_error(probe.call("POST", f"/requests/{rid}/decline", body={}, bearer=dst), 403, "forbidden")
    first = probe.call("POST", f"/requests/{rid}/decline", body={}, bearer=src)
    assert first.status_code == 200
    assert as_json(first)["status"] == "declined"
    again = probe.call("POST", f"/requests/{rid}/decline", body={}, bearer=src)
    assert again.status_code == 200
    assert as_json(again)["status"] == "declined"
    paid = as_json(
        probe.call(
            "POST",
            "/requests",
            body={"payer_handle": "srcuser", "amount": 1},
            bearer=dst,
            idem=fresh_key(),
        )
    )["request_id"]
    probe.call("POST", f"/requests/{paid}/pay", body={}, bearer=src, idem=fresh_key())
    expect_error(probe.call("POST", f"/requests/{paid}/decline", body={}, bearer=src), 409, "request_not_pending")
    expect_error(probe.call("POST", "/requests/missing/decline", body={}, bearer=src), 404, "not_found")
    expect_error(probe.call("POST", f"/requests/{rid}/decline", body={}, bearer=obs), 403, "forbidden")


def test_R97_cancel_rules(probe: Probe, seed):
    src, dst = _pair(probe)
    rid = as_json(
        probe.call(
            "POST",
            "/requests",
            body={"payer_handle": "srcuser", "amount": 1},
            bearer=dst,
            idem=fresh_key(),
        )
    )["request_id"]
    expect_error(probe.call("POST", f"/requests/{rid}/cancel", body={}, bearer=src), 403, "forbidden")
    first = probe.call("POST", f"/requests/{rid}/cancel", body={}, bearer=dst)
    assert first.status_code == 200
    assert as_json(first)["status"] == "cancelled"
    again = probe.call("POST", f"/requests/{rid}/cancel", body={}, bearer=dst)
    assert again.status_code == 200
    declined = as_json(
        probe.call(
            "POST",
            "/requests",
            body={"payer_handle": "srcuser", "amount": 1},
            bearer=dst,
            idem=fresh_key(),
        )
    )["request_id"]
    probe.call("POST", f"/requests/{declined}/decline", body={}, bearer=src)
    expect_error(probe.call("POST", f"/requests/{declined}/cancel", body={}, bearer=dst), 409, "request_not_pending")
    expect_error(probe.call("POST", "/requests/missing/cancel", body={}, bearer=dst), 404, "not_found")


def test_R98_short_request_can_be_paid_after_funds_arrive(probe: Probe, seed):
    src, dst = _pair(probe)
    p0, _ = probe.login("p0@acc.test", PASSWORD)
    amount = probe.me(src)["balance"] + 20
    rid = as_json(
        probe.call(
            "POST",
            "/requests",
            body={"payer_handle": "srcuser", "amount": amount},
            bearer=dst,
            idem=fresh_key(),
        )
    )["request_id"]
    expect_error(
        probe.call("POST", f"/requests/{rid}/pay", body={}, bearer=src, idem=fresh_key()),
        409,
        "insufficient_funds",
    )
    fund = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "srcuser", "amount": 30},
        bearer=p0,
        idem=fresh_key(),
    )
    assert fund.status_code == 201
    paid = probe.call("POST", f"/requests/{rid}/pay", body={}, bearer=src, idem=fresh_key())
    assert paid.status_code == 201


def test_R99_requests_never_appear_in_activity(probe: Probe, seed):
    src, dst = _pair(probe)
    probe.call(
        "POST",
        "/requests",
        body={"payer_handle": "srcuser", "amount": 1, "note": "hidden-from-feed"},
        bearer=dst,
        idem=fresh_key(),
    )
    for token in (src, dst):
        feed = as_json(probe.call("GET", "/activity", bearer=token))
        assert feed["payments"] == []


def test_R100_list_is_own_requests_newest_first(probe: Probe, seed):
    src, dst = _pair(probe)
    obs, _ = probe.login("obs@acc.test", PASSWORD)
    ids = []
    for _ in range(3):
        ids.append(
            as_json(
                probe.call(
                    "POST",
                    "/requests",
                    body={"payer_handle": "srcuser", "amount": 1},
                    bearer=dst,
                    idem=fresh_key(),
                )
            )["request_id"]
        )
    listed = as_json(probe.call("GET", "/requests", bearer=src))["requests"]
    assert [r["request_id"] for r in listed[:3]] == list(reversed(ids))
    foreign = as_json(probe.call("GET", "/requests", bearer=obs))["requests"]
    assert foreign == []


def test_R101_direction_filter(probe: Probe, seed):
    src, dst = _pair(probe)
    probe.call(
        "POST",
        "/requests",
        body={"payer_handle": "srcuser", "amount": 1},
        bearer=dst,
        idem=fresh_key(),
    )
    probe.call(
        "POST",
        "/requests",
        body={"payer_handle": "dstuser", "amount": 1},
        bearer=src,
        idem=fresh_key(),
    )
    incoming = as_json(probe.call("GET", "/requests", bearer=src, query={"direction": "incoming"}))
    outgoing = as_json(probe.call("GET", "/requests", bearer=src, query={"direction": "outgoing"}))
    assert incoming["requests"] and all(r["payer_handle"] == "srcuser" for r in incoming["requests"])
    assert outgoing["requests"] and all(r["requester_handle"] == "srcuser" for r in outgoing["requests"])


def test_R102_status_filter(probe: Probe, seed):
    src, dst = _pair(probe)
    pending = as_json(
        probe.call(
            "POST",
            "/requests",
            body={"payer_handle": "srcuser", "amount": 1},
            bearer=dst,
            idem=fresh_key(),
        )
    )["request_id"]
    declined = as_json(
        probe.call(
            "POST",
            "/requests",
            body={"payer_handle": "srcuser", "amount": 1},
            bearer=dst,
            idem=fresh_key(),
        )
    )["request_id"]
    probe.call("POST", f"/requests/{declined}/decline", body={}, bearer=src)
    only = as_json(probe.call("GET", "/requests", bearer=src, query={"status": "declined"}))
    assert all(r["status"] == "declined" for r in only["requests"])
    assert any(r["request_id"] == declined for r in only["requests"])
    assert all(r["request_id"] != pending for r in only["requests"])


def test_R103_list_parameter_validation(probe: Probe, seed):
    src, _ = _pair(probe)
    expect_error(probe.call("GET", "/requests", bearer=src, query={"direction": "both"}), 422, "validation_failed")
    expect_error(probe.call("GET", "/requests", bearer=src, query={"status": "open"}), 422, "validation_failed")
    expect_error(probe.call("GET", "/requests", bearer=src, query={"limit": ""}), 422, "validation_failed")
    expect_error(probe.call("GET", "/requests", bearer=src, query={"limit": "0"}), 422, "validation_failed")
    expect_error(probe.call("GET", "/requests", bearer=src, query={"limit": "201"}), 422, "validation_failed")
    ok = probe.call("GET", "/requests", bearer=src, query={"limit": "50", "offset": "0"})
    assert ok.status_code == 200


def test_R104_has_more_pagination(probe: Probe, seed):
    src, dst = _pair(probe)
    for _ in range(3):
        probe.call(
            "POST",
            "/requests",
            body={"payer_handle": "srcuser", "amount": 1},
            bearer=dst,
            idem=fresh_key(),
        )
    page = as_json(probe.call("GET", "/requests", bearer=src, query={"limit": "1", "offset": "0"}))
    assert len(page["requests"]) == 1
    assert page["has_more"] is True
    last = as_json(probe.call("GET", "/requests", bearer=src, query={"limit": "10", "offset": "0"}))
    assert last["has_more"] is False
