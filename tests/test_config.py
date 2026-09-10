import os
import pytest
from utils.config import _get_env_int, _get_env_float, _get_env_str, _get_env_bool, load_config

def test_get_env_int_fallback(monkeypatch):
    monkeypatch.setenv("TEST_INT_VALID", "42")
    monkeypatch.setenv("TEST_INT_INVALID", "not_a_number")

    assert _get_env_int("TEST_INT_VALID", 10) == 42
    assert _get_env_int("TEST_INT_INVALID", 10) == 10
    assert _get_env_int("TEST_INT_NONEXISTENT", 10) == 10

def test_get_env_float_fallback(monkeypatch):
    monkeypatch.setenv("TEST_FLOAT_VALID", "3.14")
    monkeypatch.setenv("TEST_FLOAT_INVALID", "abc")

    assert _get_env_float("TEST_FLOAT_VALID", 1.0) == 3.14
    assert _get_env_float("TEST_FLOAT_INVALID", 1.0) == 1.0
    assert _get_env_float("TEST_FLOAT_NONEXISTENT", 1.0) == 1.0

def test_get_env_bool(monkeypatch):
    monkeypatch.setenv("TEST_BOOL_TRUE", "true")
    monkeypatch.setenv("TEST_BOOL_FALSE", "0")
    monkeypatch.setenv("TEST_BOOL_INVALID", "maybe")

    assert _get_env_bool("TEST_BOOL_TRUE", False) is True
    assert _get_env_bool("TEST_BOOL_FALSE", True) is False
    assert _get_env_bool("TEST_BOOL_INVALID", True) is True

def test_load_config_defaults(monkeypatch):
    monkeypatch.setenv("MAX_WORKERS", "invalid")
    cfg = load_config()
    assert cfg.MAX_WORKERS == 6
    assert cfg.MAX_REQUESTS_PER_DOMAIN == 2
    assert cfg.HTTP_RETRIES == 3
