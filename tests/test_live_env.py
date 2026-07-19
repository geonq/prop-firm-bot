"""Tests for src/live/env.py -- .env loading, missing-creds errors, no-leak repr."""

from __future__ import annotations

import os

import pytest

from src.live.env import MissingCredentialsError, ProjectXCredentials, load_projectx_credentials


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("PROJECTX_USERNAME", raising=False)
    monkeypatch.delenv("PROJECTX_API_KEY", raising=False)


def test_loads_credentials_from_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("PROJECTX_USERNAME=geonq\nPROJECTX_API_KEY=abc123secret\n")
    creds = load_projectx_credentials(env_path=env_file)
    assert creds.username == "geonq"
    assert creds.api_key == "abc123secret"


def test_loads_credentials_from_existing_environment_variable(tmp_path, monkeypatch):
    monkeypatch.setenv("PROJECTX_USERNAME", "geonq")
    monkeypatch.setenv("PROJECTX_API_KEY", "envvarkey")
    empty_env = tmp_path / ".env"
    empty_env.write_text("")
    creds = load_projectx_credentials(env_path=empty_env)
    assert creds.username == "geonq"
    assert creds.api_key == "envvarkey"


def test_raises_when_both_missing(tmp_path):
    empty_env = tmp_path / ".env"
    empty_env.write_text("")
    with pytest.raises(MissingCredentialsError) as exc_info:
        load_projectx_credentials(env_path=empty_env)
    assert "PROJECTX_USERNAME" in str(exc_info.value)
    assert "PROJECTX_API_KEY" in str(exc_info.value)


def test_raises_when_only_api_key_missing(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("PROJECTX_USERNAME=geonq\n")
    with pytest.raises(MissingCredentialsError) as exc_info:
        load_projectx_credentials(env_path=env_file)
    assert "PROJECTX_API_KEY" in str(exc_info.value)
    assert "PROJECTX_USERNAME" not in str(exc_info.value)


def test_raises_when_value_is_blank_string(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("PROJECTX_USERNAME=geonq\nPROJECTX_API_KEY=\n")
    with pytest.raises(MissingCredentialsError):
        load_projectx_credentials(env_path=env_file)


def test_repr_redacts_api_key():
    creds = ProjectXCredentials(username="geonq", api_key="super-secret-value")
    r = repr(creds)
    assert "super-secret-value" not in r
    assert "geonq" in r
    assert "redacted" in r


def test_str_also_redacts_since_dataclass_str_uses_repr():
    creds = ProjectXCredentials(username="geonq", api_key="super-secret-value")
    assert "super-secret-value" not in str(creds)
