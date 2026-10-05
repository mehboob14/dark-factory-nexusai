from __future__ import annotations

from httpapi import (
    Probe,
    as_json,
    expect_error,
    expect_id,
    expect_json_type,
    expect_stamp,
    fresh_key,
)
from world import PASSWORD, default_world, person


def _src(probe: Probe):
    return probe.login("src@acc.test", PASSWORD)[0]


def test_R10_json_charset_on_bodies(probe: Probe, seed):
    health = probe.call("GET", "/health")
    expect_json_type(health)
    token = _src(probe)
    me = probe.call("GET", "/me", bearer=token)
    expect_json_type(me)
    pay = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1},
        bearer=token,
        idem=fresh_key(),
    )
    assert pay.status_code == 201
    expect_json_type(pay)


def test_R11_timestamps_use_numeric_offset(probe: Probe, seed):
    token = _src(probe)
    resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 2},
        bearer=token,
        idem=fresh_key(),
    )
    assert resp.status_code == 201
    expect_stamp(as_json(resp)["created_at"])


def test_R12_unknown_body_fields_are_ignored(probe: Probe, seed):
    token = _src(probe)
    resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 3, "surprise": True, "extra": {"n": 1}},
        bearer=token,
        idem=fresh_key(),
    )
    assert resp.status_code == 201, resp.text
    assert as_json(resp)["amount"] == 3


def test_R13_unknown_query_parameters_are_ignored(probe: Probe, seed):
    token = _src(probe)
    resp = probe.call("GET", "/activity", bearer=token, query={"nope": "1", "direction": "incoming"})
    assert resp.status_code == 200, resp.text
    assert "payments" in as_json(resp)


def test_R14_ids_are_opaque_and_at_most_64(probe: Probe, seed):
    token, login = probe.login("src@acc.test", PASSWORD)
    expect_id(login["user_id"])
    resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 4},
        bearer=token,
        idem=fresh_key(),
    )
    body = as_json(resp)
    expect_id(body["payment_id"])
    expect_id(body["from_user_id"])
    expect_id(body["to_user_id"])
    me = probe.me(token)
    assert me["user_id"] == "id_src"


def test_R15_single_currency_and_integer_minor_units(probe: Probe, seed):
    token = _src(probe)
    me = probe.me(token)
    assert me["currency"] == "EUR"
    assert me["minor_units"] == 2
    assert isinstance(me["balance"], int)


def test_R16_integral_json_number_forms_are_valid_amounts(probe: Probe, seed):
    token = _src(probe)
    for amount in (1000, 1000.0, 1e3):
        resp = probe.call(
            "POST",
            "/payments",
            body={"to_handle": "dstuser", "amount": amount},
            bearer=token,
            idem=fresh_key(),
        )
        assert resp.status_code == 201, (amount, resp.text)
        assert as_json(resp)["amount"] == 1000


def test_R17_correct_type_invalid_format_is_422(probe: Probe, seed):
    token = _src(probe)
    resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1000.5},
        bearer=token,
        idem=fresh_key(),
    )
    expect_error(resp, 422, "validation_failed")


def test_R18_unparseable_body_is_400_malformed_request(probe: Probe, seed):
    token = _src(probe)
    resp = probe.call(
        "POST",
        "/payments",
        raw=b"{not-json",
        bearer=token,
        idem=fresh_key(),
    )
    expect_error(resp, 400, "malformed_request")
    resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": 12, "amount": 1},
        bearer=token,
        idem=fresh_key(),
    )
    expect_error(resp, 400, "malformed_request")


def test_R19_amount_note_visibility_type_rules(probe: Probe, seed):
    token = _src(probe)
    for amount in ("1000", True, False):
        resp = probe.call(
            "POST",
            "/payments",
            body={"to_handle": "dstuser", "amount": amount},
            bearer=token,
            idem=fresh_key(),
        )
        expect_error(resp, 422, "validation_failed")
    resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1, "note": None},
        bearer=token,
        idem=fresh_key(),
    )
    expect_error(resp, 422, "validation_failed")
    resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1, "visibility": "friends"},
        bearer=token,
        idem=fresh_key(),
    )
    expect_error(resp, 422, "validation_failed")
    resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1},
        bearer=token,
        idem=fresh_key(),
    )
    assert resp.status_code == 201
    assert as_json(resp)["note"] == ""
    assert as_json(resp)["visibility"] == "public"


def test_R20_query_integers_must_be_plain_digits(probe: Probe, seed):
    token = _src(probe)
    for query in ({"limit": "1e9"}, {"limit": "4.0"}, {"limit": "+4"}, {"offset": "1e2"}):
        resp = probe.call("GET", "/requests", bearer=token, query=query)
        expect_error(resp, 422, "validation_failed")


def test_R21_shared_ranges(probe: Probe, seed):
    token = _src(probe)
    resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1},
        bearer=token,
        idem="",
    )
    expect_error(resp, 400, "missing_idempotency_key")
    resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1},
        bearer=token,
        idem="k" * 256,
    )
    expect_error(resp, 422, "validation_failed")
    resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1},
        bearer=token,
        idem="x",
    )
    assert resp.status_code == 201
    resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1},
        bearer=token,
        idem="k" * 255,
    )
    assert resp.status_code == 201
    for query, ok in (({"limit": "0"}, False), ({"limit": "1"}, True), ({"limit": "200"}, True),
                      ({"limit": "201"}, False), ({"offset": "0"}, True), ({"offset": "-1"}, False)):
        resp = probe.call("GET", "/activity", bearer=token, query=query)
        if ok:
            assert resp.status_code == 200, query
        else:
            expect_error(resp, 422, "validation_failed")


def test_R22_error_envelope(probe: Probe, seed):
    resp = probe.call("GET", "/me")
    expect_error(resp, 401, "unauthenticated")


def test_R23_garbage_inputs_are_not_5xx(probe: Probe, seed):
    token = _src(probe)
    probes = [
        probe.call("POST", "/payments", raw=b"\xff\xfe", bearer=token, idem=fresh_key()),
        probe.call("POST", "/payments", body=[], bearer=token, idem=fresh_key()),
        probe.call("POST", "/splits", body={"amount": -1, "participant_handles": None}, bearer=token, idem=fresh_key()),
        probe.call("GET", "/requests", bearer=token, query={"limit": "abc"}),
    ]
    for resp in probes:
        assert resp.status_code < 500, resp.text
        if resp.status_code >= 400:
            expect_error(resp, resp.status_code, as_json(resp)["error"]["code"])


def test_R26_balances_sum_to_seeded_total(probe: Probe, seed, total):
    observed = 0
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
        token, _ = probe.login(email, PASSWORD)
        observed += probe.me(token)["balance"]
    assert observed == total


def test_R27_failed_overdraw_leaves_no_negative(probe: Probe, seed):
    token = _src(probe)
    before = probe.me(token)["balance"]
    resp = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": before + 1},
        bearer=token,
        idem=fresh_key(),
    )
    expect_error(resp, 409, "insufficient_funds")
    after = probe.me(token)["balance"]
    assert after == before
    assert after >= 0


def test_R29_amount_cap_and_exact_integer_math(probe: Probe):
    fat = default_world()
    fat["users"] = [
        person("id_src", "src@acc.test", "srcuser", 1_000_000_000),
        person("id_dst", "dst@acc.test", "dstuser", 0),
        person("id_op", "op@acc.test", "opuser", 0),
        person("id_obs", "obs@acc.test", "obsuser", 0),
        person("id_p0", "p0@acc.test", "p0user", 0),
        person("id_p1", "p1@acc.test", "p1user", 0),
        person("id_p2", "p2@acc.test", "p2user", 0),
        person("id_p3", "p3@acc.test", "p3user", 0),
        person("id_p4", "p4@acc.test", "p4user", 0),
    ]
    probe.reset(fat)
    token = _src(probe)
    ok = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1_000_000_000},
        bearer=token,
        idem=fresh_key(),
    )
    assert ok.status_code == 201
    assert as_json(ok)["amount"] == 1_000_000_000
    bad = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1_000_000_001},
        bearer=token,
        idem=fresh_key(),
    )
    expect_error(bad, 422, "validation_failed")
    assert probe.me(token)["balance"] == 0
