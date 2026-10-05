from __future__ import annotations

from httpapi import Probe, as_json, expect_error, expect_id, expect_stamp, fresh_key, same_json
from world import PASSWORD


def _op(probe: Probe) -> str:
    return probe.login("op@acc.test", PASSWORD)[0]


def test_R130_operator_and_key_required(probe: Probe, seed):
    op = _op(probe)
    expect_error(
        probe.call(
            "POST",
            "/settlements",
            body={"transfers": [{"from_handle": "srcuser", "to_handle": "dstuser", "amount": 1}]},
            bearer=op,
        ),
        400,
        "missing_idempotency_key",
    )
    ok = probe.call(
        "POST",
        "/settlements",
        body={"transfers": [{"from_handle": "srcuser", "to_handle": "dstuser", "amount": 1}]},
        bearer=op,
        idem=fresh_key(),
    )
    assert ok.status_code == 201


def test_R131_auth_and_operator_permission(probe: Probe, seed):
    expect_error(
        probe.call(
            "POST",
            "/settlements",
            body={"transfers": [{"from_handle": "srcuser", "to_handle": "dstuser", "amount": 1}]},
            idem=fresh_key(),
        ),
        401,
        "unauthenticated",
    )
    src, _ = probe.login("src@acc.test", PASSWORD)
    expect_error(
        probe.call(
            "POST",
            "/settlements",
            body={"transfers": [{"from_handle": "srcuser", "to_handle": "dstuser", "amount": 1}]},
            bearer=src,
            idem=fresh_key(),
        ),
        403,
        "forbidden",
    )
    dst, _ = probe.login("dst@acc.test", PASSWORD)
    rid = as_json(
        probe.call(
            "POST",
            "/requests",
            body={"payer_handle": "srcuser", "amount": 1},
            bearer=dst,
            idem=fresh_key(),
        )
    )["request_id"]
    op = _op(probe)
    listed = as_json(probe.call("GET", "/requests", bearer=op))
    assert all(r["request_id"] != rid for r in listed["requests"])


def test_R132_transfers_size_bounds(probe: Probe, seed):
    op = _op(probe)
    expect_error(
        probe.call("POST", "/settlements", body={"transfers": []}, bearer=op, idem=fresh_key()),
        422,
        "validation_failed",
    )
    too_many = [{"from_handle": "srcuser", "to_handle": "dstuser", "amount": 1} for _ in range(33)]
    expect_error(
        probe.call("POST", "/settlements", body={"transfers": too_many}, bearer=op, idem=fresh_key()),
        422,
        "validation_failed",
    )
    thirty_two = [{"from_handle": "srcuser", "to_handle": "dstuser", "amount": 1} for _ in range(32)]
    resp = probe.call("POST", "/settlements", body={"transfers": thirty_two}, bearer=op, idem=fresh_key())
    assert resp.status_code == 201, resp.text


def test_R133_transfer_defaults_and_payment_rules(probe: Probe, seed):
    op = _op(probe)
    resp = as_json(
        probe.call(
            "POST",
            "/settlements",
            body={"transfers": [{"from_handle": "srcuser", "to_handle": "dstuser", "amount": 2}]},
            bearer=op,
            idem=fresh_key(),
        )
    )
    pay = resp["payments"][0]
    assert pay["note"] == ""
    assert pay["visibility"] == "public"
    expect_error(
        probe.call(
            "POST",
            "/settlements",
            body={"transfers": [{"from_handle": "srcuser", "to_handle": "dstuser", "amount": 0}]},
            bearer=op,
            idem=fresh_key(),
        ),
        422,
        "validation_failed",
    )


def test_R134_handle_self_and_shape_errors(probe: Probe, seed):
    op = _op(probe)
    expect_error(
        probe.call(
            "POST",
            "/settlements",
            body={"transfers": [{"from_handle": "ghost", "to_handle": "dstuser", "amount": 1}]},
            bearer=op,
            idem=fresh_key(),
        ),
        404,
        "not_found",
    )
    expect_error(
        probe.call(
            "POST",
            "/settlements",
            body={"transfers": [{"from_handle": "srcuser", "to_handle": "srcuser", "amount": 1}]},
            bearer=op,
            idem=fresh_key(),
        ),
        422,
        "self_payment",
    )
    expect_error(
        probe.call("POST", "/settlements", body={"transfers": "nope"}, bearer=op, idem=fresh_key()),
        422,
        "validation_failed",
    )
    expect_error(
        probe.call(
            "POST",
            "/settlements",
            body={"transfers": [{"to_handle": "dstuser", "amount": 1}]},
            bearer=op,
            idem=fresh_key(),
        ),
        422,
        "validation_failed",
    )


def test_R135_entry_errors_precede_insufficient_funds(probe: Probe, seed):
    op = _op(probe)
    resp = probe.call(
        "POST",
        "/settlements",
        body={
            "transfers": [
                {"from_handle": "missing", "to_handle": "dstuser", "amount": 9_999_999, "ignored": 1},
                {"from_handle": "srcuser", "to_handle": "dstuser", "amount": 9_999_999},
            ]
        },
        bearer=op,
        idem=fresh_key(),
    )
    expect_error(resp, 404, "not_found")


def test_R136_net_affordability(probe: Probe, seed):
    op = _op(probe)
    src, _ = probe.login("src@acc.test", PASSWORD)
    p1, _ = probe.login("p1@acc.test", PASSWORD)
    assert probe.me(p1)["balance"] == 0
    cycle = probe.call(
        "POST",
        "/settlements",
        body={
            "transfers": [
                {"from_handle": "srcuser", "to_handle": "p1user", "amount": 40},
                {"from_handle": "p1user", "to_handle": "srcuser", "amount": 40},
            ]
        },
        bearer=op,
        idem=fresh_key(),
    )
    assert cycle.status_code == 201, cycle.text
    assert probe.me(src)["balance"] == 10_000
    assert probe.me(p1)["balance"] == 0
    net = probe.call(
        "POST",
        "/settlements",
        body={
            "transfers": [
                {"from_handle": "srcuser", "to_handle": "p1user", "amount": 50},
                {"from_handle": "p1user", "to_handle": "p2user", "amount": 50},
            ]
        },
        bearer=op,
        idem=fresh_key(),
    )
    assert net.status_code == 201, net.text
    short = probe.call(
        "POST",
        "/settlements",
        body={"transfers": [{"from_handle": "p1user", "to_handle": "srcuser", "amount": 1}]},
        bearer=op,
        idem=fresh_key(),
    )
    expect_error(short, 409, "insufficient_funds")


def test_R137_all_or_nothing(probe: Probe, seed, total):
    op = _op(probe)
    src, _ = probe.login("src@acc.test", PASSWORD)
    before = probe.me(src)["balance"]
    resp = probe.call(
        "POST",
        "/settlements",
        body={
            "transfers": [
                {"from_handle": "srcuser", "to_handle": "dstuser", "amount": 1},
                {"from_handle": "p1user", "to_handle": "dstuser", "amount": 5},
            ]
        },
        bearer=op,
        idem=fresh_key(),
    )
    expect_error(resp, 409, "insufficient_funds")
    assert probe.me(src)["balance"] == before
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
        seen += tok and probe.me(tok)["balance"]
    assert seen == total


def test_R138_success_shape_and_payment_order(probe: Probe, seed):
    op = _op(probe)
    resp = probe.call(
        "POST",
        "/settlements",
        body={
            "transfers": [
                {"from_handle": "srcuser", "to_handle": "dstuser", "amount": 3, "note": "a"},
                {"from_handle": "srcuser", "to_handle": "obsuser", "amount": 4, "note": "b"},
            ]
        },
        bearer=op,
        idem=fresh_key(),
    )
    assert resp.status_code == 201
    body = as_json(resp)
    expect_id(body["settlement_id"])
    expect_stamp(body["committed_at"])
    assert [p["note"] for p in body["payments"]] == ["a", "b"]
    assert [p["amount"] for p in body["payments"]] == [3, 4]


def test_R139_member_payments_share_settlement_id_and_timestamp(probe: Probe, seed):
    op = _op(probe)
    body = as_json(
        probe.call(
            "POST",
            "/settlements",
            body={
                "transfers": [
                    {"from_handle": "srcuser", "to_handle": "dstuser", "amount": 1},
                    {"from_handle": "srcuser", "to_handle": "obsuser", "amount": 1},
                ]
            },
            bearer=op,
            idem=fresh_key(),
        )
    )
    sid = body["settlement_id"]
    for pay in body["payments"]:
        assert pay["settlement_id"] == sid
        assert pay["request_id"] is None
        assert pay["created_at"] == body["committed_at"]


def test_R140_constituents_follow_feed_visibility(probe: Probe, seed):
    op = _op(probe)
    obs, _ = probe.login("obs@acc.test", PASSWORD)
    body = as_json(
        probe.call(
            "POST",
            "/settlements",
            body={
                "transfers": [
                    {
                        "from_handle": "srcuser",
                        "to_handle": "dstuser",
                        "amount": 1,
                        "visibility": "private",
                    },
                    {
                        "from_handle": "srcuser",
                        "to_handle": "p0user",
                        "amount": 1,
                        "visibility": "public",
                    },
                ]
            },
            bearer=op,
            idem=fresh_key(),
        )
    )
    assert len(body["payments"]) == 2
    feed = {p["payment_id"] for p in as_json(probe.call("GET", "/activity", bearer=obs))["payments"]}
    assert body["payments"][0]["payment_id"] not in feed
    assert body["payments"][1]["payment_id"] in feed


def test_R141_settlement_replay_is_200_original_body(probe: Probe, seed):
    op = _op(probe)
    key = fresh_key()
    payload = {"transfers": [{"from_handle": "srcuser", "to_handle": "dstuser", "amount": 1}]}
    first = probe.call("POST", "/settlements", body=payload, bearer=op, idem=key)
    replay = probe.call("POST", "/settlements", body=payload, bearer=op, idem=key)
    assert first.status_code == 201
    assert replay.status_code == 200
    assert same_json(as_json(first), as_json(replay))


def test_R142_reset_and_import_preserve_operator_and_settlement(probe: Probe, seed):
    op = _op(probe)
    key = fresh_key()
    first = probe.call(
        "POST",
        "/settlements",
        body={"transfers": [{"from_handle": "srcuser", "to_handle": "dstuser", "amount": 6}]},
        bearer=op,
        idem=key,
    )
    assert first.status_code == 201
    snap = probe.export()
    probe.import_state(snap)
    replay = probe.call(
        "POST",
        "/settlements",
        body={"transfers": [{"from_handle": "srcuser", "to_handle": "dstuser", "amount": 6}]},
        bearer=op,
        idem=key,
    )
    assert replay.status_code == 200
    assert same_json(as_json(first), as_json(replay))
    still_op = probe.call(
        "POST",
        "/settlements",
        body={"transfers": [{"from_handle": "srcuser", "to_handle": "dstuser", "amount": 1}]},
        bearer=op,
        idem=fresh_key(),
    )
    assert still_op.status_code == 201
