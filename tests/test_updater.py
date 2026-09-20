"""Tests for updater semver comparison, update checking, and compiler routing."""
from __future__ import annotations

import pytest

from keraunos.compiler import OfflineIntentCompiler
from keraunos.updater import is_newer_version, _parse_version


def test_parse_version():
    assert _parse_version("1.0.2") == (1, 0, 2)
    assert _parse_version("v1.0.3") == (1, 0, 3)
    assert _parse_version("v2.1.0-beta") == (2, 1, 0)


def test_is_newer_version():
    assert is_newer_version("1.0.3", "1.0.2") is True
    assert is_newer_version("1.1.0", "1.0.2") is True
    assert is_newer_version("2.0.0", "1.0.2") is True
    assert is_newer_version("1.0.2", "1.0.2") is False
    assert is_newer_version("1.0.1", "1.0.2") is False


def test_compiler_routes_app_update_intent():
    compiler = OfflineIntentCompiler()

    for phrase in ["check for updates", "update keraunos", "upgrade keraunos", "update this app", "check app updates"]:
        state, diags = compiler.compile(phrase)
        resolved = [d.resolved_target for d in diags]
        assert "check_app_updates" in resolved, f"Failed for phrase: {phrase}"
