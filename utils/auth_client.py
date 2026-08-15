# =============================================================================
# NicksFix — Desktop Auth Client
#
# Talks to server/auth_server.py, persists the session token in the OS
# keyring (Windows Credential Manager / macOS Keychain / Linux Secret
# Service — whatever `keyring` resolves to on this platform), and binds every
# call to this machine's HWID via utils.hwid.compute_host_id().
#
# The JWT itself never touches disk in plaintext — only the keyring. A small
# non-secret marker file (just the username, so the right keyring entry can
# be found again) lives under the platform's per-user config directory.
# =============================================================================

import json
import os
from dataclasses import dataclass

import keyring
import requests

from utils.hwid import compute_host_id
from utils.paths import config_dir

SERVICE_NAME = "NicksFix"
DEFAULT_BASE_URL = "http://192.168.1.127:8000"
REQUEST_TIMEOUT = 6  # seconds — keeps a dead/offline server from freezing the caller

# =============================================================================
# !!! DEBUG LOGIN BACKDOOR — REMOVE BEFORE ANY PUBLIC RELEASE !!!
#
# A hardcoded credential that bypasses the auth server entirely and drops
# straight into a full-access (admin / diamond) session, even with the server
# offline. This exists purely to make local development and UI testing quick
# while the auth server is a moving target in pre-alpha.
#
# SECURITY: anyone who reads this source (it ships unobfuscated) gets a
# permanent admin key that ignores HWID licensing and works offline. This is
# only acceptable because NicksFix is pre-alpha and unreleased. Flip
# DEBUG_BYPASS_ENABLED to False (or delete this block and the guard in
# login()) before the app is distributed to anyone.
# =============================================================================
DEBUG_BYPASS_ENABLED = True
DEBUG_USERNAME = "Debug"
DEBUG_PASSWORD = "Testing123123!"


@dataclass
class AuthResult:
    """
    Outcome of an auth operation, with enough detail for the UI to show a
    specific message rather than a generic "login failed".

    status is one of:
        ok, invalid_credentials, hwid_mismatch, rate_limited,
        username_taken, weak_password, offline, server_error, no_session
    """
    ok: bool
    status: str
    message: str
    username: str | None = None
    role: str | None = None
    tier: str | None = None


SESSION_FILE = os.path.join(config_dir(), "session.json")


class AuthClient:
    """
    Usage:
        client = AuthClient()
        result = client.login("nick", "hunter2")
        if result.ok:
            ...proceed with result.role
    """

    def __init__(self, base_url: str | None = None):
        self.base_url = (
            base_url
            or os.environ.get("NICKSFIX_AUTH_URL", DEFAULT_BASE_URL)
        ).rstrip("/")
        self.hwid = compute_host_id()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def register(self, username: str, password: str) -> AuthResult:
        try:
            resp = requests.post(
                f"{self.base_url}/auth/register",
                json={"username": username, "password": password, "hwid": self.hwid},
                timeout=REQUEST_TIMEOUT,
            )
        except requests.exceptions.RequestException as e:
            return self._offline_result(e)

        if resp.status_code == 201:
            data = resp.json()
            self._persist_session(username, data["access_token"])
            return AuthResult(True, "ok", "Account created.", username, data["role"],
                               data.get("tier", "free"))

        if resp.status_code == 409:
            return AuthResult(False, "username_taken", "That username is already taken.")
        if resp.status_code == 422:
            return AuthResult(False, "weak_password", self._detail(resp))

        return AuthResult(False, "server_error", self._detail(resp))

    def login(self, username: str, password: str) -> AuthResult:
        # ---- DEBUG LOGIN BACKDOOR (see DEBUG_* constants above) ----
        # Intercept before any network call so it works with the server
        # offline. role="admin" + tier="diamond" gives full tab access and
        # bypasses every tier gate (see utils/tiers.has_tier_access). No token
        # is persisted, so this session does not survive a restart — that's
        # intentional; a backdoor shouldn't leave a saved-session artifact.
        if (DEBUG_BYPASS_ENABLED
                and username == DEBUG_USERNAME
                and password == DEBUG_PASSWORD):
            return AuthResult(
                True, "ok", "Signed in (DEBUG bypass — no server auth).",
                username=DEBUG_USERNAME, role="admin", tier="diamond",
            )

        try:
            resp = requests.post(
                f"{self.base_url}/auth/login",
                json={"username": username, "password": password, "hwid": self.hwid},
                timeout=REQUEST_TIMEOUT,
            )
        except requests.exceptions.RequestException as e:
            return self._offline_result(e)

        if resp.status_code == 200:
            data = resp.json()
            self._persist_session(username, data["access_token"])
            return AuthResult(True, "ok", "Signed in.", username, data["role"],
                               data.get("tier", "free"))

        if resp.status_code == 401:
            return AuthResult(False, "invalid_credentials", "Incorrect username or password.")
        if resp.status_code == 403:
            return AuthResult(False, "hwid_mismatch", self._detail(resp))
        if resp.status_code == 429:
            return AuthResult(False, "rate_limited", self._detail(resp))

        return AuthResult(False, "server_error", self._detail(resp))

    def verify_saved_session(self) -> AuthResult:
        """Check keyring for a saved token and validate it against the server."""
        username = self._read_session_username()
        if not username:
            return AuthResult(False, "no_session", "No saved session.")

        token = keyring.get_password(SERVICE_NAME, username)
        if not token:
            self._clear_session()
            return AuthResult(False, "no_session", "No saved session.")

        try:
            resp = requests.get(
                f"{self.base_url}/auth/verify",
                headers={"Authorization": f"Bearer {token}"},
                timeout=REQUEST_TIMEOUT,
            )
        except requests.exceptions.RequestException as e:
            # Offline is not "logged out" — leave the saved session in place
            # so the user isn't kicked out just because the server is
            # temporarily unreachable. The caller decides what to do (e.g.
            # let the user work in a degraded/guest mode, or retry).
            return self._offline_result(e)

        if resp.status_code == 200:
            data = resp.json()
            return AuthResult(True, "ok", "Session restored.", data["username"], data["role"],
                               data.get("tier", "free"))

        # Any other response means the token is no longer good — clear it
        # so the app doesn't keep retrying a dead session.
        self._clear_session()
        return AuthResult(False, "invalid_credentials", "Saved session is no longer valid.")

    def logout(self):
        username = self._read_session_username()
        if username:
            try:
                keyring.delete_password(SERVICE_NAME, username)
            except keyring.errors.PasswordDeleteError:
                pass
        self._clear_session()

    # -------------------------------------------------------------------------
    # Internals
    # -------------------------------------------------------------------------

    @staticmethod
    def _detail(resp: requests.Response) -> str:
        try:
            data = resp.json()
        except ValueError:
            return resp.text or f"Server returned {resp.status_code}."
        detail = data.get("detail", data)
        if isinstance(detail, list):  # FastAPI validation errors
            return "; ".join(str(d.get("msg", d)) for d in detail)
        return str(detail)

    @staticmethod
    def _offline_result(exc: Exception) -> AuthResult:
        return AuthResult(
            False, "offline",
            "Cannot reach the auth server. Check your connection or try again shortly.",
        )

    def _persist_session(self, username: str, token: str):
        keyring.set_password(SERVICE_NAME, username, token)
        with open(SESSION_FILE, "w", encoding="utf-8") as handle:
            json.dump({"username": username}, handle)

    @staticmethod
    def _read_session_username() -> str | None:
        if not os.path.isfile(SESSION_FILE):
            return None
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as handle:
                return json.load(handle).get("username")
        except (json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def _clear_session():
        try:
            os.remove(SESSION_FILE)
        except FileNotFoundError:
            pass
