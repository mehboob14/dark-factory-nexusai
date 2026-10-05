from __future__ import annotations

from httpapi import Probe, as_json, expect_error, expect_id, fresh_key, walk_contains
from world import PASSWORD


def test_R42_handle_unique_matches_pattern_and_never_changes(probe: Probe, seed):
    token, _ = probe.login("src@acc.test", PASSWORD)
    first = probe.me(token)["handle"]
    assert first == "srcuser"
    later, _ = probe.login("src@acc.test", PASSWORD)
    assert probe.me(later)["handle"] == first
    created, _ = probe.signup("src2@acc.test", PASSWORD, "X")
    assert probe.me(created)["handle"] == "src2"
    assert probe.me(created)["handle"] != first


def test_R43_seeded_handle_comes_from_fixture(probe: Probe, seed):
    token, _ = probe.login("obs@acc.test", PASSWORD)
    assert probe.me(token)["handle"] == "obsuser"


def test_R44_signup_derives_handle_from_email_local_part(probe: Probe, seed):
    token, body = probe.signup("Local.Part+tag@acc.test", PASSWORD, "LP")
    me = probe.me(token)
    assert me["handle"] == "local_part_tag"
    assert body["display_name"] == "LP"
    expect_id(body["user_id"])
    long_token, _ = probe.signup("twentyonecharsxxxxxx@acc.test", PASSWORD, "Long")
    assert probe.me(long_token)["handle"] == "twentyonecharsxxxxxx"


def test_R45_taken_derived_handle_is_409_and_creates_no_account(probe: Probe, seed):
    resp = probe.call(
        "POST",
        "/auth/signup",
        body={"email": "srcuser@other.test", "password": "password1", "display_name": "Clash"},
    )
    expect_error(resp, 409, "handle_taken")
    login = probe.call(
        "POST",
        "/auth/login",
        body={"email": "srcuser@other.test", "password": "password1"},
    )
    expect_error(login, 401, "unauthenticated")


def test_R46_new_user_starts_at_zero_and_can_receive(probe: Probe, seed):
    token, _ = probe.signup("newbie@acc.test", PASSWORD, "New")
    me = probe.me(token)
    assert me["balance"] == 0
    src, _ = probe.login("src@acc.test", PASSWORD)
    from httpapi import fresh_key

    pay = probe.call(
        "POST",
        "/payments",
        body={"to_handle": me["handle"], "amount": 15},
        bearer=src,
        idem=fresh_key(),
    )
    assert pay.status_code == 201
    assert probe.me(token)["balance"] == 15
    req = probe.call(
        "POST",
        "/requests",
        body={"payer_handle": me["handle"], "amount": 2},
        bearer=src,
        idem=fresh_key(),
    )
    assert req.status_code == 201


def test_R47_signup_shape(probe: Probe, seed):
    resp = probe.call(
        "POST",
        "/auth/signup",
        body={"email": "shape@acc.test", "password": PASSWORD, "display_name": "Shape"},
    )
    assert resp.status_code == 201
    body = as_json(resp)
    assert set(body) >= {"user_id", "display_name", "token"}
    assert body["display_name"] == "Shape"
    assert "total" not in body


def test_R48_login_shape(probe: Probe, seed):
    resp = probe.call("POST", "/auth/login", body={"email": "src@acc.test", "password": PASSWORD})
    assert resp.status_code == 200
    body = as_json(resp)
    assert set(body) >= {"user_id", "display_name", "token"}
    assert body["user_id"] == "id_src"


def test_R49_email_taken(probe: Probe, seed):
    resp = probe.call(
        "POST",
        "/auth/signup",
        body={"email": "src@acc.test", "password": PASSWORD, "display_name": "Dup"},
    )
    expect_error(resp, 409, "email_taken")


def test_R50_password_shorter_than_8_is_422(probe: Probe, seed):
    resp = probe.call(
        "POST",
        "/auth/signup",
        body={"email": "short@acc.test", "password": "1234567", "display_name": "S"},
    )
    expect_error(resp, 422, "validation_failed")
    resp = probe.call(
        "POST",
        "/auth/signup",
        body={"email": "eight@acc.test", "password": "12345678", "display_name": "E"},
    )
    assert resp.status_code == 201


def test_R51_email_must_be_local_at_domain(probe: Probe, seed):
    for email in ("nodomain", "a@", "@b", "a@b c", "a@@b", ""):
        resp = probe.call(
            "POST",
            "/auth/signup",
            body={"email": email, "password": PASSWORD, "display_name": "E"},
        )
        expect_error(resp, 422, "validation_failed")
    resp = probe.call(
        "POST",
        "/auth/signup",
        body={"email": "a@b", "password": PASSWORD, "display_name": "Ok"},
    )
    assert resp.status_code == 201, resp.text


def test_R52_wrong_password_or_unknown_email_is_401(probe: Probe, seed):
    expect_error(
        probe.call("POST", "/auth/login", body={"email": "src@acc.test", "password": "wrong-pass"}),
        401,
        "unauthenticated",
    )
    expect_error(
        probe.call("POST", "/auth/login", body={"email": "missing@acc.test", "password": PASSWORD}),
        401,
        "unauthenticated",
    )


def test_R53_bearer_required_except_public_paths(probe: Probe, seed):
    public = [
        ("GET", "/health", None),
        ("POST", "/_test/reset", default_reset_body()),
        ("POST", "/auth/signup", {"email": "pub@acc.test", "password": PASSWORD, "display_name": "P"}),
        ("POST", "/auth/login", {"email": "src@acc.test", "password": PASSWORD}),
        ("GET", "/_test/export", None),
    ]
    for method, path, body in public:
        resp = probe.call(method, path, body=body, wait=12 if path.startswith("/_test") else None)
        assert resp.status_code < 400 or resp.status_code == 409, (path, resp.status_code, resp.text)
    for path in ("/me", "/activity", "/requests", "/payments"):
        method = "GET" if path != "/payments" else "POST"
        kwargs = {"body": {"to_handle": "dstuser", "amount": 1}} if method == "POST" else {}
        resp = probe.call(method, path, **kwargs)
        expect_error(resp, 401, "unauthenticated")
    expect_error(probe.call("GET", "/me", headers={"Authorization": "Bearer"}), 401, "unauthenticated")
    expect_error(probe.call("GET", "/me", headers={"Authorization": "Token abc"}), 401, "unauthenticated")
    expect_error(probe.call("GET", "/me", bearer="unknown-token"), 401, "unauthenticated")


def default_reset_body():
    from world import default_world

    return default_world()


def test_R53_import_is_public(probe: Probe, seed):
    snap = probe.export()
    resp = probe.import_state(snap, expect_ok=False)
    assert resp.status_code == 204


def test_R54_tokens_do_not_expire_and_multiple_sessions_live(probe: Probe, seed):
    a, _ = probe.login("src@acc.test", PASSWORD)
    b, _ = probe.login("src@acc.test", PASSWORD)
    assert a != b
    assert probe.me(a)["user_id"] == probe.me(b)["user_id"] == "id_src"
    c, _ = probe.signup("multi@acc.test", PASSWORD, "Multi")
    d, _ = probe.login("multi@acc.test", PASSWORD)
    assert probe.me(c)["handle"] == probe.me(d)["handle"]


def test_R55_export_does_not_contain_plaintext_passwords(probe: Probe, seed):
    snap = probe.export()
    assert not walk_contains(snap, PASSWORD)
    probe.signup("hashme@acc.test", "hash-secret-99", "Hash")
    snap2 = probe.export()
    assert not walk_contains(snap2, "hash-secret-99")
    token, _ = probe.login("hashme@acc.test", "hash-secret-99")
    assert probe.me(token)["display_name"] == "Hash"


def test_R56_me_shape(probe: Probe, seed):
    token, _ = probe.login("src@acc.test", PASSWORD)
    me = probe.me(token)
    assert me["user_id"] == "id_src"
    assert me["display_name"] == "srcuser"
    assert me["handle"] == "srcuser"
    assert me["balance"] == 10_000
    assert me["currency"] == "EUR"
    assert me["minor_units"] == 2
    for leaked in ("available", "held", "total", "authorization_id"):
        assert leaked not in me


def test_R53_token_is_checked_before_idempotency_or_body(probe: Probe, seed):
    expect_error(
        probe.call("POST", "/payments", raw=b"{not json", idem=fresh_key()),
        401,
        "unauthenticated",
    )
    expect_error(
        probe.call("POST", "/payments", body={"to_handle": "dstuser", "amount": 1}),
        401,
        "unauthenticated",
    )
