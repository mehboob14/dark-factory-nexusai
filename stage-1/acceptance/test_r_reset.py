from __future__ import annotations

import copy

from httpapi import Probe, as_json, expect_error
from world import PASSWORD, SHORT_SEEDED_PASSWORD, default_world, fixture, person


def test_R31_reset_is_unauthenticated_and_returns_204(probe: Probe):
    resp = probe.reset(default_world(), expect_ok=False)
    assert resp.status_code == 204
    assert not resp.text.strip()


def test_R32_reset_replaces_world_and_can_repeat(probe: Probe):
    first = default_world()
    probe.reset(first)
    token, _ = probe.login("src@acc.test", PASSWORD)
    assert probe.me(token)["balance"] == 10_000
    second = fixture(
        users=[
            person("id_only", "only@acc.test", "onlyone", 77),
        ]
    )
    probe.reset(second)
    old = probe.call("POST", "/auth/login", body={"email": "src@acc.test", "password": PASSWORD})
    expect_error(old, 401, "unauthenticated")
    token2, _ = probe.login("only@acc.test", PASSWORD)
    assert probe.me(token2)["balance"] == 77
    probe.reset(second)
    token3, _ = probe.login("only@acc.test", PASSWORD)
    assert probe.me(token3)["balance"] == 77


def test_R33_reset_clears_tokens_payments_and_imports(probe: Probe, seed):
    token, _ = probe.login("src@acc.test", PASSWORD)
    from httpapi import fresh_key

    probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 9},
        bearer=token,
        idem=fresh_key(),
    )
    snap = probe.export()
    probe.import_state(snap)
    probe.reset(default_world())
    later = probe.call("GET", "/me", bearer=token)
    expect_error(later, 401, "unauthenticated")
    fresh, _ = probe.login("src@acc.test", PASSWORD)
    feed = probe.call("GET", "/activity", bearer=fresh)
    assert as_json(feed)["payments"] == []


def test_R34_seeded_users_login_immediately(probe: Probe, seed):
    token, body = probe.login("src@acc.test", PASSWORD)
    assert body["user_id"] == "id_src"
    assert body["display_name"] == "srcuser"
    assert isinstance(token, str) and token


def test_R35_seeded_balance_is_not_replayed_against_payments(probe: Probe):
    world = fixture(
        users=[
            person("id_src", "src@acc.test", "srcuser", 100),
            person("id_dst", "dst@acc.test", "dstuser", 50),
        ],
        payments=[
            {
                "id": "pay_seed",
                "from_user_id": "id_src",
                "to_user_id": "id_dst",
                "amount": 25,
                "note": "already-netted",
                "visibility": "public",
            }
        ],
    )
    probe.reset(world)
    src, _ = probe.login("src@acc.test", PASSWORD)
    dst, _ = probe.login("dst@acc.test", PASSWORD)
    assert probe.me(src)["balance"] == 100
    assert probe.me(dst)["balance"] == 50


def test_R36_negative_balance_is_422_and_state_unchanged(probe: Probe, seed):
    token, _ = probe.login("src@acc.test", PASSWORD)
    before = probe.me(token)
    bad = default_world()
    bad["users"][0]["balance"] = -1
    resp = probe.reset(bad, expect_ok=False)
    expect_error(resp, 422, "validation_failed")
    token2, _ = probe.login("src@acc.test", PASSWORD)
    assert probe.me(token2)["balance"] == before["balance"]


def test_R37_minor_units_accepted_and_rejected(probe: Probe):
    for currency, minor in (("EUR", 2), ("JPY", 0), ("BHD", 3)):
        body = fixture(
            currency=currency,
            minor_units=minor,
            users=[person("id_src", "src@acc.test", "srcuser", 10)],
        )
        resp = probe.reset(body, expect_ok=False)
        assert resp.status_code == 204, (currency, minor, resp.text)
        token, _ = probe.login("src@acc.test", PASSWORD)
        me = probe.me(token)
        assert me["currency"] == currency
        assert me["minor_units"] == minor
    keep = fixture(users=[person("id_src", "src@acc.test", "srcuser", 3)])
    probe.reset(keep)
    bad = fixture(minor_units=1, users=[person("id_src", "src@acc.test", "srcuser", 3)])
    resp = probe.reset(bad, expect_ok=False)
    expect_error(resp, 422, "validation_failed")
    token, _ = probe.login("src@acc.test", PASSWORD)
    assert probe.me(token)["balance"] == 3


def test_R38_seeded_payments_and_requests_are_visible(probe: Probe):
    world = fixture(
        users=[
            person("id_src", "src@acc.test", "srcuser", 80),
            person("id_dst", "dst@acc.test", "dstuser", 20),
        ],
        payments=[
            {
                "id": "pay_seeded",
                "from_user_id": "id_src",
                "to_user_id": "id_dst",
                "amount": 7,
                "note": "seed-note",
                "visibility": "private",
            }
        ],
        requests=[
            {
                "id": "req_seeded",
                "requester_id": "id_dst",
                "payer_id": "id_src",
                "amount": 11,
                "note": "seed-ask",
                "status": "pending",
            }
        ],
    )
    probe.reset(world)
    src, _ = probe.login("src@acc.test", PASSWORD)
    feed = as_json(probe.call("GET", "/activity", bearer=src))
    assert any(p["payment_id"] == "pay_seeded" and p["note"] == "seed-note" for p in feed["payments"])
    listed = as_json(probe.call("GET", "/requests", bearer=src))
    assert any(r["request_id"] == "req_seeded" and r["status"] == "pending" for r in listed["requests"])


def test_R39_settlement_operator_ids_default_and_apply(probe: Probe):
    none = fixture(users=[person("id_src", "src@acc.test", "srcuser", 50), person("id_dst", "dst@acc.test", "dstuser", 0)])
    probe.reset(none)
    src, _ = probe.login("src@acc.test", PASSWORD)
    from httpapi import fresh_key

    denied = probe.call(
        "POST",
        "/settlements",
        body={"transfers": [{"from_handle": "srcuser", "to_handle": "dstuser", "amount": 1}]},
        bearer=src,
        idem=fresh_key(),
    )
    expect_error(denied, 403, "forbidden")
    world = default_world()
    probe.reset(world)
    op, _ = probe.login("op@acc.test", PASSWORD)
    ok = probe.call(
        "POST",
        "/settlements",
        body={"transfers": [{"from_handle": "srcuser", "to_handle": "dstuser", "amount": 1}]},
        bearer=op,
        idem=fresh_key(),
    )
    assert ok.status_code == 201, ok.text


def test_R40_invalid_fixtures_are_422_and_change_nothing(probe: Probe, seed):
    token, _ = probe.login("src@acc.test", PASSWORD)
    keep = probe.me(token)["balance"]
    cases = [
        fixture(users=[person("dup", "a@acc.test", "aaaa", 1), person("dup", "b@acc.test", "bbbb", 1)]),
        fixture(users=[person("a", "same@acc.test", "aaaa", 1), person("b", "same@acc.test", "bbbb", 1)]),
        fixture(users=[person("a", "a@acc.test", "same", 1), person("b", "b@acc.test", "same", 1)]),
        fixture(users=[person("a", "a@acc.test", "BadHandle", 1)]),
        fixture(
            users=[person("id_src", "src@acc.test", "srcuser", 1)],
            payments=[{"id": "p", "from_user_id": "missing", "to_user_id": "id_src", "amount": 1, "visibility": "public"}],
        ),
        fixture(
            users=[person("id_src", "src@acc.test", "srcuser", 1)],
            payments=[{"id": "p" * 65, "from_user_id": "id_src", "to_user_id": "id_src", "amount": 1, "visibility": "public"}],
        ),
        fixture(
            users=[person("id_src", "src@acc.test", "srcuser", 1)],
            payments=[{"id": "p", "from_user_id": "id_src", "to_user_id": "id_src", "amount": 1, "visibility": "secret"}],
        ),
        {"minor_units": 2, "users": [person("id_src", "src@acc.test", "srcuser", 1)]},
        {"currency": "EUR", "users": [person("id_src", "src@acc.test", "srcuser", 1)]},
        {"currency": "EUR", "minor_units": 2},
    ]
    for body in cases:
        resp = probe.reset(body, expect_ok=False)
        expect_error(resp, 422, "validation_failed")
        token2, _ = probe.login("src@acc.test", PASSWORD)
        assert probe.me(token2)["balance"] == keep


def test_R40_invalid_json_reset_is_400(probe: Probe, seed):
    token, _ = probe.login("src@acc.test", PASSWORD)
    keep = probe.me(token)["balance"]
    resp = probe.call("POST", "/_test/reset", raw=b"{", wait=12)
    expect_error(resp, 400, "malformed_request")
    token2, _ = probe.login("src@acc.test", PASSWORD)
    assert probe.me(token2)["balance"] == keep


def test_R41_fixture_amount_types_and_negatives(probe: Probe, seed):
    token, _ = probe.login("src@acc.test", PASSWORD)
    keep = probe.me(token)["balance"]
    users = [person("id_src", "src@acc.test", "srcuser", 10), person("id_dst", "dst@acc.test", "dstuser", 0)]
    bad_amount = fixture(
        users=users,
        payments=[{"id": "p", "from_user_id": "id_src", "to_user_id": "id_dst", "amount": -3, "visibility": "public"}],
    )
    expect_error(probe.reset(bad_amount, expect_ok=False), 422, "validation_failed")
    wrong = copy.deepcopy(default_world())
    wrong["users"][0]["balance"] = "10"
    expect_error(probe.reset(wrong, expect_ok=False), 400, "malformed_request")
    token2, _ = probe.login("src@acc.test", PASSWORD)
    assert probe.me(token2)["balance"] == keep


def test_R34_seeded_short_password_still_logs_in(probe: Probe):
    world = fixture(
        users=[person("id_src", "src@acc.test", "srcuser", 1, password=SHORT_SEEDED_PASSWORD)]
    )
    probe.reset(world)
    token, _ = probe.login("src@acc.test", SHORT_SEEDED_PASSWORD)
    assert probe.me(token)["handle"] == "srcuser"
