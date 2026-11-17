import pyotp

from app.core.config import get_settings
from tests.conftest import PASSWORD, Api, last_email_token, signup


def _login(api: Api, email: str, password: str = PASSWORD) -> object:
    return api.post("/auth/login", {"email": email, "password": password})


def test_signup_creates_owner_workspace() -> None:
    api = signup("owner@a.example", "Agency A", name="Ann Owner")
    me = api.get("/auth/me").json()
    assert me["email"] == "owner@a.example"
    assert me["active_tenant"]["role"] == "agency_owner"
    assert "member.invite" in me["permissions"]
    assert me["scope"] == "tenant"
    assert api.get("/audit-log").json()["items"][0]["action"] in {"member.added", "tenant.created"}


def test_signup_duplicate_email_conflict() -> None:
    signup("dup@a.example", "A")
    r = Api().post("/auth/signup", {"email": "DUP@a.example", "name": "x", "password": PASSWORD, "agency_name": "B"})
    assert r.status_code == 409


def test_weak_password_rejected() -> None:
    r = Api().post("/auth/signup", {"email": "w@a.example", "name": "x", "password": "short", "agency_name": "B"})
    assert r.status_code == 422


def test_login_errors_are_generic() -> None:
    signup("u@a.example", "A")
    wrong = _login(Api(), "u@a.example", "wrong password!!")
    unknown = _login(Api(), "nobody@a.example", "wrong password!!")
    assert wrong.status_code == unknown.status_code == 401  # type: ignore[attr-defined]
    assert wrong.json()["detail"] == unknown.json()["detail"]  # type: ignore[attr-defined]


def test_login_issues_new_session_and_logout_revokes_it() -> None:
    signup("u@a.example", "A")
    api = Api()
    assert _login(api, "u@a.example").status_code == 200  # type: ignore[attr-defined]
    cookie_name = get_settings().session_cookie_name
    first = api.c.cookies.get(cookie_name)
    assert first and api.get("/auth/me").status_code == 200
    assert _login(api, "u@a.example").status_code == 200  # type: ignore[attr-defined]
    assert api.c.cookies.get(cookie_name) != first  # rotated
    stolen = Api()
    stolen.c.cookies.set(cookie_name, first)
    assert stolen.get("/auth/me").status_code == 200  # old session still valid until logout of that session
    assert stolen.post("/auth/logout").status_code == 204
    replay = Api()
    replay.c.cookies.set(cookie_name, first)
    assert replay.get("/auth/me").status_code == 401


def test_session_cookie_flags() -> None:
    api = Api()
    r = api.post("/auth/signup", {"email": "c@a.example", "name": "x", "password": PASSWORD, "agency_name": "B"})
    header = r.headers["set-cookie"].lower()
    assert "httponly" in header and "samesite=lax" in header and "path=/" in header


def test_unauthenticated_access_denied() -> None:
    assert Api().get("/clients").status_code == 401
    assert Api().get("/auth/me").status_code == 401


def test_csrf_required_on_unsafe_methods() -> None:
    api = signup("u@a.example", "A")
    r = api.c.post("/api/v1/clients", json={"name": "x"})  # no header
    assert r.status_code == 403
    r = api.c.post("/api/v1/clients", json={"name": "x"}, headers={"X-CSRF-Token": "forged-value"})
    assert r.status_code == 403
    assert api.post("/clients", {"name": "x"}).status_code == 201


def test_cross_origin_unsafe_request_rejected() -> None:
    api = signup("u@a.example", "A")
    r = api.c.post("/api/v1/clients", json={"name": "x"},
                   headers={"X-CSRF-Token": api.csrf, "Origin": "https://evil.example"})
    assert r.status_code == 403


def test_security_headers_present() -> None:
    r = Api().get("/healthz")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-request-id"]


def test_login_rate_limited_per_account() -> None:
    signup("u@a.example", "A")
    statuses = [_login(Api(), "u@a.example", "bad password!!").status_code for _ in range(10)]  # type: ignore
    assert statuses[:8] == [401] * 8
    assert statuses[8] == 429
    # Even the correct password is refused while locked out.
    assert _login(Api(), "u@a.example").status_code == 429  # type: ignore[attr-defined]


def test_password_reset_flow_revokes_sessions() -> None:
    api = signup("u@a.example", "A")
    anon = Api()
    r1 = anon.post("/auth/password/forgot", {"email": "u@a.example"})
    r2 = anon.post("/auth/password/forgot", {"email": "missing@a.example"})
    assert r1.status_code == r2.status_code == 202 and r1.json() == r2.json()  # no enumeration
    token = last_email_token("/reset-password")
    assert anon.post("/auth/password/reset", {"token": token, "password": "a brand new passphrase"}).status_code == 204
    assert api.get("/auth/me").status_code == 401  # existing sessions revoked
    assert anon.post("/auth/password/reset", {"token": token, "password": "another passphrase!"}).status_code == 400
    assert _login(Api(), "u@a.example").status_code == 401  # type: ignore[attr-defined]
    assert _login(Api(), "u@a.example", "a brand new passphrase").status_code == 200  # type: ignore[attr-defined]


def test_change_password_revokes_other_sessions() -> None:
    a = signup("u@a.example", "A")
    b = Api()
    _login(b, "u@a.example")
    r = a.post("/auth/password/change", {"current_password": PASSWORD, "new_password": "new passphrase 123"})
    assert r.status_code == 204
    assert a.get("/auth/me").status_code == 200
    assert b.get("/auth/me").status_code == 401
    bad = a.post("/auth/password/change", {"current_password": "nope nope nope", "new_password": "x" * 14})
    assert bad.status_code == 400


def test_mfa_enrolment_login_and_recovery_codes() -> None:
    api = signup("m@a.example", "A")
    setup = api.post("/auth/mfa/setup").json()
    totp = pyotp.TOTP(setup["secret"])
    assert api.post("/auth/mfa/enable", {"code": "000000" if totp.now() != "000000" else "111111"}).status_code == 400
    codes = api.post("/auth/mfa/enable", {"code": totp.now()}).json()["recovery_codes"]
    assert len(codes) == 10
    assert api.get("/auth/me").json()["mfa_enabled"] is True

    # Password alone yields an MFA-pending session that cannot access data.
    s = Api()
    assert _login(s, "m@a.example").json() == {"mfa_required": True}  # type: ignore[attr-defined]
    assert s.get("/auth/me").status_code == 401
    assert s.get("/clients").status_code == 401
    assert s.post("/auth/mfa/verify-login", {"code": "123456" if totp.now() != "123456" else "654321"}
                  ).status_code == 401
    assert s.post("/auth/mfa/verify-login", {"code": totp.now()}).status_code == 200
    assert s.get("/auth/me").status_code == 200

    # Recovery code works once.
    r = Api()
    _login(r, "m@a.example")
    assert r.post("/auth/mfa/verify-login", {"code": codes[0]}).status_code == 200
    r2 = Api()
    _login(r2, "m@a.example")
    assert r2.post("/auth/mfa/verify-login", {"code": codes[0]}).status_code == 401


def test_mfa_secret_is_encrypted_at_rest(owner_engine: object) -> None:
    from sqlalchemy import text

    api = signup("m@a.example", "A")
    secret = api.post("/auth/mfa/setup").json()["secret"]
    with owner_engine.connect() as c:  # type: ignore[attr-defined]
        stored = c.execute(text("SELECT mfa_secret_enc FROM users")).scalar()
    assert stored and secret not in stored


def test_signup_can_be_disabled(monkeypatch: object) -> None:
    s = get_settings()
    monkeypatch.setattr(s, "allow_signup", False)  # type: ignore[attr-defined]
    r = Api().post("/auth/signup", {"email": "x@a.example", "name": "x", "password": PASSWORD, "agency_name": "B"})
    assert r.status_code == 403
