from __future__ import annotations

from httpapi import Probe, as_json, expect_error, expect_id, expect_stamp, fresh_key
from world import PASSWORD


def _src(probe: Probe) -> str:
    return probe.login("src@acc.test", PASSWORD)[0]


def test_R105_split_creates_pending_requests(probe: Probe, seed):
    token = _src(probe)
    resp = probe.call(
        "POST",
        "/splits",
        body={"amount": 9, "participant_handles": ["srcuser", "dstuser", "obsuser"]},
        bearer=token,
        idem=fresh_key(),
    )
    assert resp.status_code == 201
    body = as_json(resp)
    assert len(body["requests"]) == 2
    assert all(r["status"] == "pending" for r in body["requests"])


def test_R106_split_body_and_handle_order(probe: Probe, seed):
    token = _src(probe)
    resp = as_json(
        probe.call(
            "POST",
            "/splits",
            body={"amount": 10, "participant_handles": ["p0user", "p1user", "p2user"], "note": "tab"},
            bearer=token,
            idem=fresh_key(),
        )
    )
    assert [s["handle"] for s in resp["shares"]] == ["p0user", "p1user", "p2user"]
    assert resp["note"] == "tab"


def test_R107_caller_omitted_still_creates_others_requests(probe: Probe, seed):
    token = _src(probe)
    resp = as_json(
        probe.call(
            "POST",
            "/splits",
            body={"amount": 6, "participant_handles": ["dstuser", "obsuser"]},
            bearer=token,
            idem=fresh_key(),
        )
    )
    assert [s["handle"] for s in resp["shares"]] == ["dstuser", "obsuser"]
    assert {r["payer_handle"] for r in resp["requests"]} == {"dstuser", "obsuser"}
    assert all(r["requester_handle"] == "srcuser" for r in resp["requests"])


def test_R108_split_success_shape(probe: Probe, seed):
    token = _src(probe)
    resp = probe.call(
        "POST",
        "/splits",
        body={"amount": 3, "participant_handles": ["dstuser"]},
        bearer=token,
        idem=fresh_key(),
    )
    assert resp.status_code == 201
    body = as_json(resp)
    for key in ("split_id", "amount", "currency", "note", "shares", "requests", "created_at"):
        assert key in body
    expect_id(body["split_id"])
    expect_stamp(body["created_at"])
    assert body["amount"] == 3
    assert body["currency"] == "EUR"


def test_R109_shares_cover_everyone_and_sum_to_amount(probe: Probe, seed):
    token = _src(probe)
    body = as_json(
        probe.call(
            "POST",
            "/splits",
            body={"amount": 1000, "participant_handles": ["p0user", "p1user", "p2user"]},
            bearer=token,
            idem=fresh_key(),
        )
    )
    assert [s["handle"] for s in body["shares"]] == ["p0user", "p1user", "p2user"]
    assert sum(s["amount"] for s in body["shares"]) == 1000
    assert all(set(s) == {"handle", "amount"} for s in body["shares"])


def test_R110_requests_are_full_objects_excluding_caller(probe: Probe, seed):
    token = _src(probe)
    body = as_json(
        probe.call(
            "POST",
            "/splits",
            body={"amount": 9, "participant_handles": ["srcuser", "dstuser"]},
            bearer=token,
            idem=fresh_key(),
        )
    )
    assert len(body["requests"]) == 1
    req = body["requests"][0]
    assert req["payer_handle"] == "dstuser"
    assert req["requester_handle"] == "srcuser"
    assert req["status"] == "pending"
    assert req["payment_id"] is None
    assert "request_id" in req
    assert "created_at" in req


def test_R111_split_amount_boundaries(probe: Probe, seed):
    token = _src(probe)
    for amount in (0, 1_000_000_001, 3.5):
        expect_error(
            probe.call(
                "POST",
                "/splits",
                body={"amount": amount, "participant_handles": ["dstuser"]},
                bearer=token,
                idem=fresh_key(),
            ),
            422,
            "validation_failed",
        )


def test_R112_empty_or_duplicate_participants(probe: Probe, seed):
    token = _src(probe)
    expect_error(
        probe.call(
            "POST",
            "/splits",
            body={"amount": 1, "participant_handles": []},
            bearer=token,
            idem=fresh_key(),
        ),
        422,
        "validation_failed",
    )
    expect_error(
        probe.call(
            "POST",
            "/splits",
            body={"amount": 1, "participant_handles": ["dstuser", "dstuser"]},
            bearer=token,
            idem=fresh_key(),
        ),
        422,
        "validation_failed",
    )
    expect_error(
        probe.call(
            "POST",
            "/splits",
            body={"amount": 1, "participant_handles": ["ghostuser", "ghostuser"]},
            bearer=token,
            idem=fresh_key(),
        ),
        422,
        "validation_failed",
    )


def test_R113_split_note_too_long(probe: Probe, seed):
    token = _src(probe)
    expect_error(
        probe.call(
            "POST",
            "/splits",
            body={"amount": 1, "participant_handles": ["dstuser"], "note": "z" * 201},
            bearer=token,
            idem=fresh_key(),
        ),
        422,
        "validation_failed",
    )


def test_R114_unknown_participant_is_404(probe: Probe, seed):
    token = _src(probe)
    expect_error(
        probe.call(
            "POST",
            "/splits",
            body={"amount": 1, "participant_handles": ["dstuser", "ghostuser"]},
            bearer=token,
            idem=fresh_key(),
        ),
        404,
        "not_found",
    )


def test_R115_caller_only_split_has_empty_requests(probe: Probe, seed):
    token = _src(probe)
    body = as_json(
        probe.call(
            "POST",
            "/splits",
            body={"amount": 7, "participant_handles": ["srcuser"]},
            bearer=token,
            idem=fresh_key(),
        )
    )
    assert body["shares"] == [{"handle": "srcuser", "amount": 7}]
    assert body["requests"] == []


def test_R116_split_does_not_check_balances(probe: Probe, seed):
    token = probe.login("p1@acc.test", PASSWORD)[0]
    assert probe.me(token)["balance"] == 0
    resp = probe.call(
        "POST",
        "/splits",
        body={"amount": 500, "participant_handles": ["srcuser", "dstuser"]},
        bearer=token,
        idem=fresh_key(),
    )
    assert resp.status_code == 201, resp.text


def test_R117_shares_differ_by_at_most_one(probe: Probe, seed):
    token = _src(probe)
    body = as_json(
        probe.call(
            "POST",
            "/splits",
            body={"amount": 10, "participant_handles": ["p0user", "p1user", "p2user"]},
            bearer=token,
            idem=fresh_key(),
        )
    )
    amounts = [s["amount"] for s in body["shares"]]
    assert max(amounts) - min(amounts) <= 1
    assert sum(amounts) == 10


def test_R118_required_share_examples(probe: Probe, seed):
    token = _src(probe)
    cases = [
        (1000, ["p0user", "p1user", "p2user"], [334, 333, 333]),
        (1, ["p0user", "p1user", "p2user"], [1, 0, 0]),
        (10, ["p0user", "p1user", "p2user"], [4, 3, 3]),
        (999, ["p0user", "p1user", "p2user"], [333, 333, 333]),
        (5, ["p0user", "p1user", "p2user", "p3user", "p4user"], [1, 1, 1, 1, 1]),
    ]
    for amount, handles, expected in cases:
        body = as_json(
            probe.call(
                "POST",
                "/splits",
                body={"amount": amount, "participant_handles": handles},
                bearer=token,
                idem=fresh_key(),
            )
        )
        assert [s["amount"] for s in body["shares"]] == expected, (amount, body["shares"])


def test_R119_zero_share_still_creates_a_request(probe: Probe, seed):
    token = _src(probe)
    body = as_json(
        probe.call(
            "POST",
            "/splits",
            body={"amount": 1, "participant_handles": ["p0user", "p1user", "p2user"]},
            bearer=token,
            idem=fresh_key(),
        )
    )
    assert body["shares"][2]["amount"] == 0
    zero = next(r for r in body["requests"] if r["payer_handle"] == "p2user")
    assert zero["amount"] == 0
    assert zero["status"] == "pending"


def test_R120_order_changes_who_gets_the_extra_unit(probe: Probe, seed):
    token = _src(probe)
    a = as_json(
        probe.call(
            "POST",
            "/splits",
            body={"amount": 10, "participant_handles": ["p0user", "p1user", "p2user"]},
            bearer=token,
            idem=fresh_key(),
        )
    )
    b = as_json(
        probe.call(
            "POST",
            "/splits",
            body={"amount": 10, "participant_handles": ["p2user", "p1user", "p0user"]},
            bearer=token,
            idem=fresh_key(),
        )
    )
    assert [s["amount"] for s in a["shares"]] == [4, 3, 3]
    assert [s["amount"] for s in b["shares"]] == [4, 3, 3]
    assert a["shares"][0]["handle"] == "p0user"
    assert b["shares"][0]["handle"] == "p2user"


def test_R121_split_is_not_a_feed_item(probe: Probe, seed):
    token = _src(probe)
    probe.call(
        "POST",
        "/splits",
        body={"amount": 4, "participant_handles": ["dstuser"]},
        bearer=token,
        idem=fresh_key(),
    )
    feed = as_json(probe.call("GET", "/activity", bearer=token))
    assert feed["payments"] == []
    dst, _ = probe.login("dst@acc.test", PASSWORD)
    listed = as_json(probe.call("GET", "/requests", bearer=dst))
    assert listed["requests"]


def test_R30_paid_splits_conserve_seeded_total(probe: Probe, seed, total):
    token = _src(probe)
    body = as_json(
        probe.call(
            "POST",
            "/splits",
            body={"amount": 9, "participant_handles": ["srcuser", "p0user", "dstuser"]},
            bearer=token,
            idem=fresh_key(),
        )
    )
    for req in body["requests"]:
        payer = probe.login(
            {"p0user": "p0@acc.test", "dstuser": "dst@acc.test"}[req["payer_handle"]],
            PASSWORD,
        )[0]
        if probe.me(payer)["balance"] < req["amount"]:
            continue
        pay = probe.call(
            "POST",
            f"/requests/{req['request_id']}/pay",
            body={},
            bearer=payer,
            idem=fresh_key(),
        )
        assert pay.status_code == 201
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
