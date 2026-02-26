"""JWT authentication for agent-to-backend HTTP requests.

Manages a bearer token obtained during agent registration and injects
it into all outbound requests via a shared httpx.AsyncClient.

Security: Token and credentials are stored in macOS Keychain via the
`security` CLI. Falls back to environment variables for CI/testing.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

KEYCHAIN_SERVICE = "com.kmflow.agent"


def _read_keychain(account: str) -> str | None:
    """Read a secret from macOS Keychain via the security CLI."""
    try:
        result = subprocess.run(
            [
                "security", "find-generic-password",
                "-s", KEYCHAIN_SERVICE,
                "-a", account,
                "-w",  # output password only
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.debug("Keychain read failed for account=%s", account)
    return None


def _write_keychain(account: str, secret: str) -> bool:
    """Write a secret to macOS Keychain via the security CLI."""
    # Delete existing entry first (ignore errors if not found)
    subprocess.run(
        ["security", "delete-generic-password", "-s", KEYCHAIN_SERVICE, "-a", account],
        capture_output=True,
        timeout=5,
    )
    try:
        result = subprocess.run(
            [
                "security", "add-generic-password",
                "-s", KEYCHAIN_SERVICE,
                "-a", account,
                "-w", secret,
                "-U",  # update if exists
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_auth_token() -> str | None:
    """Read the agent JWT from Keychain, environment, or legacy token file.

    Priority: env var > Keychain > legacy file (migrated to Keychain on read).
    """
    # 1. Environment variable (CI/testing)
    token = os.environ.get("KMFLOW_AGENT_TOKEN")
    if token:
        return token

    # 2. macOS Keychain
    token = _read_keychain("agent_token")
    if token:
        return token

    # 3. Legacy file — migrate to Keychain and remove file
    token_path = Path(
        os.path.expanduser("~/Library/Application Support/KMFlowAgent/.agent_token")
    )
    try:
        token = token_path.read_text().strip()
        if token:
            if _write_keychain("agent_token", token):
                token_path.unlink(missing_ok=True)
                logger.info("Migrated agent token from file to Keychain")
            return token
    except OSError:
        pass

    return None


def _get_ca_bundle_path() -> str | None:
    """Return path to bundled CA certificate for server verification."""
    # Look for bundled CA cert in app bundle resources
    bundle_contents = os.environ.get("KMFLOW_BUNDLE_CONTENTS", "")
    if bundle_contents:
        ca_path = Path(bundle_contents) / "Resources" / "ca-bundle.crt"
        if ca_path.exists():
            return str(ca_path)
    return None


def _get_client_cert() -> tuple[str, str] | None:
    """Return (cert_path, key_path) for mTLS client certificate."""
    app_support = Path(
        os.path.expanduser("~/Library/Application Support/KMFlowAgent")
    )
    cert_path = app_support / "client.crt"
    key_path = app_support / "client.key"
    if cert_path.exists() and key_path.exists():
        return (str(cert_path), str(key_path))
    return None


def create_http_client(token: str | None = None) -> httpx.AsyncClient:
    """Create a shared httpx.AsyncClient with auth headers and TLS config."""
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # TLS verification: use bundled CA cert if available, else system default
    ca_bundle = _get_ca_bundle_path()
    verify: str | bool = ca_bundle if ca_bundle else True

    # mTLS: use client certificate if enrolled
    client_cert = _get_client_cert()
    cert = client_cert if client_cert else None

    return httpx.AsyncClient(
        headers=headers,
        timeout=30.0,
        verify=verify,
        cert=cert,
    )
