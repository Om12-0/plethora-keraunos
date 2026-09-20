"""Tests for the secret scanner."""
from keraunos.scanner import (
    assert_no_secrets,
    scan_text_detailed,
    scan_text_for_secrets,
)


def test_sk_key_detected():
    text = "api_key=sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD"
    assert scan_text_for_secrets(text), "expected sk-style key to be flagged"


def test_github_token_detected():
    text = "token ghp_" + "A" * 36
    assert scan_text_for_secrets(text)


def test_clean_text_passes():
    assert scan_text_for_secrets("install 7zip and neovim, dark mode") == []
    assert_no_secrets("winget: 7zip.7zip")  # should not raise


def test_private_key_detected():
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIE..."
    findings = scan_text_detailed(text)
    assert findings, "expected SSH private key header to be flagged"


def test_secret_blocks_persist():
    import pytest
    with pytest.raises(ValueError):
        assert_no_secrets("key = sk-" + "x" * 40, context="unit-test")
