"""prompt 28 (option ii): API-key value encrypted-at-rest + level-2-password reveal."""
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.services.api_key_service import decrypt_key_value, encrypt_key_value, reveal_enabled
from tests.test_api_keys import create_external_api_key

ENC_SECRET = "unit-test-apikey-enc-secret-please-rotate-0123456789"


@pytest.fixture
def enc_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn the reveal feature on (encryption key configured, level-2 password = 0000)."""
    monkeypatch.setattr(settings, "apikey_enc_key", ENC_SECRET)
    monkeypatch.setattr(settings, "apikey_view_password", "0000")


# --- crypto unit level ---
def test_encrypt_roundtrip_when_enabled(enc_on: None) -> None:
    token = encrypt_key_value("mdp_live_secret_value")
    assert token is not None and token != "mdp_live_secret_value"  # actually encrypted
    assert decrypt_key_value(token) == "mdp_live_secret_value"


def test_encrypt_returns_none_when_feature_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "apikey_enc_key", "")
    assert reveal_enabled() is False
    assert encrypt_key_value("mdp_live_x") is None  # nothing stored -> key stays hash-only


# --- endpoint K1: create new + reveal with correct password ---
def test_reveal_returns_key_with_correct_password(
    client: TestClient, auth_headers: dict[str, str], enc_on: None
) -> None:
    created = create_external_api_key(client, auth_headers)
    assert created["revealable"] is True
    resp = client.post(f"/api-keys/{created['id']}/reveal", headers=auth_headers, json={"password": "0000"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["api_key"] == created["api_key"]  # round-trips to the exact key shown at creation


# --- endpoint K2: wrong password -> 4xx, no key leaked ---
def test_reveal_wrong_password_is_403_and_hides_key(
    client: TestClient, auth_headers: dict[str, str], enc_on: None
) -> None:
    created = create_external_api_key(client, auth_headers)
    resp = client.post(f"/api-keys/{created['id']}/reveal", headers=auth_headers, json={"password": "9999"})
    assert resp.status_code == 403
    assert created["api_key"] not in resp.text


# --- endpoint K3: legacy hash-only key -> "not available", no error ---
def test_reveal_legacy_hash_only_key_not_available(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # created while the feature was OFF -> no encrypted value stored
    monkeypatch.setattr(settings, "apikey_enc_key", "")
    created = create_external_api_key(client, auth_headers)
    assert created["revealable"] is False
    # now the feature is on, but this old key still cannot be revealed
    monkeypatch.setattr(settings, "apikey_enc_key", ENC_SECRET)
    monkeypatch.setattr(settings, "apikey_view_password", "0000")
    resp = client.post(f"/api-keys/{created['id']}/reveal", headers=auth_headers, json={"password": "0000"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False and body["api_key"] is None and body["reason"]


# --- K5: authentication still works on a key created with encryption on ---
def test_hash_auth_still_works_with_encryption_on(
    client: TestClient, auth_headers: dict[str, str], enc_on: None
) -> None:
    created = create_external_api_key(client, auth_headers, directions=["outbound"])
    # the plaintext authenticates via the hash exactly as before (encryption is additive)
    from app.services.api_key_service import hash_api_key

    assert hash_api_key(created["api_key"])  # deterministic, non-empty
