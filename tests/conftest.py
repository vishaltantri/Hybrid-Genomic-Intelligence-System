import pytest

from backend.app import hardening, security, store


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    hardening.limiter.reset()
    yield
    hardening.limiter.reset()


@pytest.fixture(autouse=True)
def _provision_token_users(request, monkeypatch):
    """Many suites mint tokens for ad-hoc users on throw-away databases. current_user now requires the account to exist
    (Phase 17), so for those suites make sure a validly signed token's user row exists. Tests marked `strict_auth`
    (tests/test_security.py) opt out and exercise the real behaviour."""
    if request.node.get_closest_marker("strict_auth"):
        yield
        return
    real = security.decode_token

    def decode(token):
        payload = real(token)
        if not store.get_user(str(payload["sub"])):
            store.create_user(str(payload["sub"]), payload["role"], "!test-no-login", "")
        return payload

    monkeypatch.setattr(security, "decode_token", decode)
    yield
