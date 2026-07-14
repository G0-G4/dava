"""
Dedicated xAI OAuth (device code) credential management for dava.

This module gives dava its own independent Grok Imagine OAuth grant
(access_token + refresh_token) separate from any Hermes Agent running
on the same machine.

Key properties:
- Uses the public xAI OAuth client (same as Hermes xai-oauth).
- Device-code flow (server-friendly, no local browser required).
- Proactive + reactive refresh with ~1h skew.
- Refresh tokens are single-use; we handle races conservatively.
- Tokens stored in a simple JSON file (0600) pointed to by xai_auth_path.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import aiohttp

from dava.errors import RequestError
from dava.generators.hermes_auth import mask_token  # reuse safe masking

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (sourced from current Hermes Agent xai-oauth implementation)
# ---------------------------------------------------------------------------

XAI_OAUTH_ISSUER = "https://auth.x.ai"
XAI_OAUTH_CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
XAI_OAUTH_SCOPE = "openid profile email offline_access grok-cli:access api:access"

DEVICE_CODE_URL = f"{XAI_OAUTH_ISSUER}/oauth2/device/code"
TOKEN_URL = f"{XAI_OAUTH_ISSUER}/oauth2/token"

# xAI access tokens are relatively short-lived (~6h). Hermes uses a 1h skew
# for long-running/cron workloads so we do the same.
XAI_ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 3600

# Use exactly the same User-Agent as Hermes Agent for all xAI calls
# (OAuth device flow + /images + /videos). This ensures compatibility.
HERMES_XAI_USER_AGENT = "Hermes-Agent/1.0"

# Default location if caller does not provide an explicit path.
# The actual path used at runtime comes from global config (xai_auth_path).
DEFAULT_XAI_AUTH_PATH = "~/.dava/xai_auth.json"

# Polling / timeout defaults for device login
DEVICE_POLL_INTERVAL = 5
DEVICE_POLL_TIMEOUT = 300  # 5 minutes


# ---------------------------------------------------------------------------
# Low-level HTTP helpers
# ---------------------------------------------------------------------------

async def _post_form(url: str, data: dict[str, str], timeout: int = 30) -> dict:
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": HERMES_XAI_USER_AGENT,
    }
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
        async with session.post(url, data=data, headers=headers) as resp:
            text = await resp.text()
            if resp.status != 200:
                # Try to surface useful error body
                try:
                    err = await resp.json()
                except Exception:
                    err = {"raw": text}
                raise RequestError(f"xAI OAuth POST failed: {resp.status} {err}")
            return await resp.json()


# ---------------------------------------------------------------------------
# Device code flow (used by init script)
# ---------------------------------------------------------------------------

async def start_xai_device_login() -> dict[str, Any]:
    """
    Begin a device-code login against xAI.

    Returns the device code response containing:
      - device_code
      - user_code
      - verification_uri (and often verification_uri_complete)
      - expires_in, interval
    """
    payload = {
        "client_id": XAI_OAUTH_CLIENT_ID,
        "scope": XAI_OAUTH_SCOPE,
    }
    data = await _post_form(DEVICE_CODE_URL, payload)
    logger.info("xAI device code obtained. user_code=%s verification_uri=%s",
                data.get("user_code"), data.get("verification_uri"))
    return data


async def poll_xai_device_code(
    device_code: str,
    *,
    interval: int = DEVICE_POLL_INTERVAL,
    timeout: int = DEVICE_POLL_TIMEOUT,
) -> dict[str, Any]:
    """
    Poll the token endpoint until the user approves the device code
    or we hit a terminal error / timeout.
    """
    payload_base = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": XAI_OAUTH_CLIENT_ID,
        "device_code": device_code,
    }

    deadline = time.monotonic() + timeout
    current_interval = interval

    while time.monotonic() < deadline:
        try:
            data = await _post_form(TOKEN_URL, payload_base, timeout=15)
            # Success
            if "access_token" in data:
                logger.info("xAI device login succeeded (new independent grant)")
                return data
        except RequestError as e:
            # xAI returns 400 with JSON error for pending states
            msg = str(e)
            if "authorization_pending" in msg:
                await asyncio.sleep(current_interval)
                continue
            if "slow_down" in msg:
                current_interval = min(current_interval + 5, 15)
                await asyncio.sleep(current_interval)
                continue
            if "expired_token" in msg or "access_denied" in msg:
                raise RequestError(
                    "xAI device code expired or access denied. "
                    "Please start a new login."
                ) from e
            # Other errors are fatal
            raise

        await asyncio.sleep(current_interval)

    raise RequestError("xAI device login timed out. Please try again.")


# ---------------------------------------------------------------------------
# Token storage (dedicated file for dava)
# ---------------------------------------------------------------------------

def _resolve_path(auth_path: Optional[str]) -> Path:
    if auth_path:
        return Path(auth_path).expanduser()
    return Path(DEFAULT_XAI_AUTH_PATH).expanduser()


async def load_xai_tokens(auth_path: Optional[str] = None) -> Optional[dict]:
    """Load the stored tokens. Returns None if file missing or unreadable."""
    path = _resolve_path(auth_path)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
        if isinstance(raw, dict) and raw.get("access_token"):
            return raw
        return None
    except Exception as e:
        logger.warning(f"Could not read xAI auth file {path}: {e}")
        return None


async def save_xai_tokens(auth_path: Optional[str], tokens: dict) -> Path:
    """
    Atomically write tokens to the target file and chmod 0600.
    Returns the resolved path.
    """
    path = _resolve_path(auth_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Prepare payload with metadata
    payload = {
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "token_type": tokens.get("token_type", "Bearer"),
        "expires_in": tokens.get("expires_in"),
        "scope": tokens.get("scope"),
        "last_refresh": datetime.now(timezone.utc).isoformat(),
        "obtained_at": tokens.get("obtained_at") or datetime.now(timezone.utc).isoformat(),
    }

    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(json.dumps(payload, indent=2) + "\n")
        tmp.chmod(0o600)
        tmp.replace(path)
        path.chmod(0o600)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass

    logger.debug(f"xAI tokens saved to {path} (access+refresh rotated)")
    return path


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------

async def refresh_xai_oauth(refresh_token: str) -> dict:
    """
    Exchange a refresh_token for a fresh access+refresh pair.
    Raises RequestError on failure (including terminal cases).
    """
    if not refresh_token:
        raise RequestError("No refresh_token available for xAI OAuth")

    data = {
        "grant_type": "refresh_token",
        "client_id": XAI_OAUTH_CLIENT_ID,
        "refresh_token": refresh_token,
    }

    try:
        resp = await _post_form(TOKEN_URL, data, timeout=20)
    except RequestError as e:
        # Detect common terminal refresh failures
        msg = str(e).lower()
        if any(x in msg for x in ("invalid_grant", "refresh_token_reused", "expired", "revoked")):
            raise RequestError(
                "xAI refresh token is no longer valid (invalid_grant / reused / revoked). "
                "You must obtain a new token by running the init script again."
            ) from e
        raise

    if "access_token" not in resp:
        raise RequestError(f"xAI refresh did not return access_token: {resp}")

    logger.info("xAI OAuth token refreshed successfully (new access+refresh pair)")
    return resp


def _needs_refresh(tokens: dict) -> bool:
    """Heuristic: refresh if we are within the skew window or have no last_refresh."""
    last = tokens.get("last_refresh")
    expires_in = tokens.get("expires_in") or 21600  # fallback ~6h

    if not last:
        return True

    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - last_dt).total_seconds()
        # Refresh early
        return age > (expires_in - XAI_ACCESS_TOKEN_REFRESH_SKEW_SECONDS)
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Public API used by generators
# ---------------------------------------------------------------------------

async def get_xai_access_token(
    auth_path: Optional[str] = None,
    *,
    force_refresh: bool = False,
) -> str:
    """
    Return a valid (fresh if needed) access_token.

    - Loads from the dedicated xai_auth_path file.
    - Performs proactive refresh when close to expiry.
    - On 401 from caller, the caller should call with force_refresh=True and retry.
    """
    tokens = await load_xai_tokens(auth_path)
    if not tokens or not tokens.get("access_token"):
        raise RequestError(
            "No xAI OAuth token found for dava. "
            "Run `uv run scripts/init_xai_auth.py` (as the user that runs the bot) "
            "to obtain a dedicated token, then set image_generator=hermes and/or "
            "video_generator=hermes (and xai_auth_path if non-default)."
        )

    if force_refresh or _needs_refresh(tokens):
        if not tokens.get("refresh_token"):
            raise RequestError(
                "xAI token is missing refresh_token. Re-run the init script."
            )
        try:
            refreshed = await refresh_xai_oauth(tokens["refresh_token"])
            # Merge what we got
            new_tokens = {**tokens, **refreshed}
            await save_xai_tokens(auth_path, new_tokens)
            tokens = new_tokens
        except RequestError:
            # Re-raise with context already added inside refresh
            raise

    token = tokens["access_token"]
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Using xAI token (masked={mask_token(token)})")
    logger.info(f"xAI token ready (masked={mask_token(token)})")
    return token


# Convenience for the init script
async def perform_full_device_login_and_save(auth_path: Optional[str] = None) -> Path:
    """
    Interactive (from script) device login flow + persist result.
    Returns the path where tokens were written.
    """
    logger.info("Starting xAI device-code login for dava (independent grant)...")
    dc = await start_xai_device_login()

    uri = dc.get("verification_uri_complete") or dc.get("verification_uri")
    user_code = dc.get("user_code", "")
    print("\n=== xAI Grok OAuth Login for dava ===")
    print(f"1. Open this URL in any browser: {uri}")
    if user_code:
        print(f"2. Enter code when prompted: {user_code}")
    print("3. Approve access for 'Grok' / xAI.")
    print("Waiting for approval...\n")

    tokens = await poll_xai_device_code(
        dc["device_code"],
        interval=dc.get("interval", DEVICE_POLL_INTERVAL),
        timeout=dc.get("expires_in", DEVICE_POLL_TIMEOUT) + 30,
    )

    # Normalize
    tokens.setdefault("obtained_at", datetime.now(timezone.utc).isoformat())
    path = await save_xai_tokens(auth_path, tokens)
    print(f"\n✅ Success. Tokens saved to: {path}")
    print("   You can now set in global config:")
    print("     image_generator=hermes")
    print("     video_generator=hermes")
    print("   (optionally) xai_auth_path=... if you used a non-default location.")
    return path
