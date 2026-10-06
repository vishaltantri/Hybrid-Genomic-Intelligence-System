import pytest

from backend.app import hardening, security, store


@pytest.fixture(autouse=True)
def _no_live_llm_symptoms(monkeypatch):
    monkeypatch.setenv("GENOMERA_LLM_SYMPTOMS", "0")      # tests must not call a live model unless they stub it
    yield


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


@pytest.fixture(autouse=True)
def _isolated_default_db(tmp_path, monkeypatch):
    """Phase 30: a test that forgets its own database must never write into the developer's data/genomind_dev.sqlite3
    (earlier runs left orphan analyses/events there). Suites that need a specific database still set their own after this."""
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "default_test.sqlite3")
    store.init_db()
    yield
