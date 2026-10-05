from __future__ import annotations

from httpapi import Probe, as_json, expect_error, fresh_key
from world import PASSWORD


def _login(probe: Probe, email: str) -> str:
    return probe.login(email, PASSWORD)[0]


def test_R122_activity_is_payments_newest_first(probe: Probe, seed):
    src = _login(probe, "src@acc.test")
    ids = []
    for _ in range(3):
        resp = probe.call(
            "POST",
            "/payments",
            body={"to_handle": "dstuser", "amount": 1},
            bearer=src,
            idem=fresh_key(),
        )
        ids.append(as_json(resp)["payment_id"])
    feed = as_json(probe.call("GET", "/activity", bearer=src))
    assert [p["payment_id"] for p in feed["payments"][:3]] == list(reversed(ids))


def test_R123_visibility_rule(probe: Probe, seed):
    src = _login(probe, "src@acc.test")
    dst = _login(probe, "dst@acc.test")
    obs = _login(probe, "obs@acc.test")
    pub = as_json(
        probe.call(
            "POST",
            "/payments",
            body={"to_handle": "dstuser", "amount": 1, "visibility": "public"},
            bearer=src,
            idem=fresh_key(),
        )
    )
    priv = as_json(
        probe.call(
            "POST",
            "/payments",
            body={"to_handle": "dstuser", "amount": 1, "visibility": "private"},
            bearer=src,
            idem=fresh_key(),
        )
    )
    obs_feed = {p["payment_id"] for p in as_json(probe.call("GET", "/activity", bearer=obs))["payments"]}
    src_feed = {p["payment_id"] for p in as_json(probe.call("GET", "/activity", bearer=src))["payments"]}
    dst_feed = {p["payment_id"] for p in as_json(probe.call("GET", "/activity", bearer=dst))["payments"]}
    assert pub["payment_id"] in obs_feed
    assert priv["payment_id"] not in obs_feed
    assert pub["payment_id"] in src_feed and priv["payment_id"] in src_feed
    assert pub["payment_id"] in dst_feed and priv["payment_id"] in dst_feed


def test_R124_requests_never_in_activity(probe: Probe, seed):
    src = _login(probe, "src@acc.test")
    dst = _login(probe, "dst@acc.test")
    probe.call(
        "POST",
        "/requests",
        body={"payer_handle": "srcuser", "amount": 1},
        bearer=dst,
        idem=fresh_key(),
    )
    assert as_json(probe.call("GET", "/activity", bearer=src))["payments"] == []


def test_R125_private_visible_to_receiver(probe: Probe, seed):
    src = _login(probe, "src@acc.test")
    dst = _login(probe, "dst@acc.test")
    priv = as_json(
        probe.call(
            "POST",
            "/payments",
            body={"to_handle": "dstuser", "amount": 1, "visibility": "private"},
            bearer=src,
            idem=fresh_key(),
        )
    )
    dst_ids = [p["payment_id"] for p in as_json(probe.call("GET", "/activity", bearer=dst))["payments"]]
    assert priv["payment_id"] in dst_ids


def test_R126_visibility_is_one_value_for_everyone(probe: Probe, seed):
    src = _login(probe, "src@acc.test")
    dst = _login(probe, "dst@acc.test")
    pay = as_json(
        probe.call(
            "POST",
            "/payments",
            body={"to_handle": "dstuser", "amount": 1, "visibility": "public"},
            bearer=src,
            idem=fresh_key(),
        )
    )
    for token in (src, dst, _login(probe, "obs@acc.test")):
        item = next(
            p
            for p in as_json(probe.call("GET", "/activity", bearer=token))["payments"]
            if p["payment_id"] == pay["payment_id"]
        )
        assert item["visibility"] == "public"


def test_R127_activity_response_shape(probe: Probe, seed):
    src = _login(probe, "src@acc.test")
    probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1},
        bearer=src,
        idem=fresh_key(),
    )
    body = as_json(probe.call("GET", "/activity", bearer=src))
    assert set(body) >= {"payments", "has_more"}
    pay = body["payments"][0]
    for key in (
        "payment_id",
        "from_user_id",
        "to_user_id",
        "amount",
        "note",
        "visibility",
        "request_id",
        "settlement_id",
        "created_at",
    ):
        assert key in pay


def test_R128_activity_limit_offset_match_requests(probe: Probe, seed):
    src = _login(probe, "src@acc.test")
    expect_error(probe.call("GET", "/activity", bearer=src, query={"limit": "0"}), 422, "validation_failed")
    expect_error(probe.call("GET", "/activity", bearer=src, query={"limit": "201"}), 422, "validation_failed")
    expect_error(probe.call("GET", "/activity", bearer=src, query={"offset": "-1"}), 422, "validation_failed")
    expect_error(probe.call("GET", "/activity", bearer=src, query={"limit": "4.0"}), 422, "validation_failed")
    ok = probe.call("GET", "/activity", bearer=src, query={"limit": "1", "offset": "0"})
    assert ok.status_code == 200


def test_R129_same_second_order_unspecified_but_list_is_complete(probe: Probe, seed):
    src = _login(probe, "src@acc.test")
    created = set()
    for _ in range(4):
        created.add(
            as_json(
                probe.call(
                    "POST",
                    "/payments",
                    body={"to_handle": "dstuser", "amount": 1},
                    bearer=src,
                    idem=fresh_key(),
                )
            )["payment_id"]
        )
    listed = {p["payment_id"] for p in as_json(probe.call("GET", "/activity", bearer=src))["payments"]}
    assert created <= listed
