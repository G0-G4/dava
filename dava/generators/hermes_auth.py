import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_HERMES_AUTH_PATH = "~/.hermes/auth.json"


def mask_token(token: str) -> str:
    """Return a safe masked version of a token for logging (public helper)."""
    if not token:
        return "<empty>"
    if len(token) <= 8:
        return "*" * len(token)
    return token[:6] + "..." + token[-4:]


# Backwards compat for internal use
_mask_token = mask_token


def get_hermes_xai_access_token(auth_path: Optional[str] = None) -> str:
    """
    Extract the xAI Grok OAuth access token that Hermes obtained via
    `hermes model` / `hermes auth add xai-oauth`.

    The token is stored by Hermes in ~/.hermes/auth.json after a successful
    browser OAuth login (SuperGrok or X Premium+).

    This allows dava to call the *real* https://api.x.ai endpoints directly
    using the same credentials the user already provisioned through Hermes.

    Returns the raw access_token string suitable for "Authorization: Bearer ..."

    Raises RequestError if no token can be found.
    """
    from dava.errors import RequestError

    candidates = []

    if auth_path:
        candidates.append(auth_path)

    # Common locations
    candidates.extend([
        os.environ.get("HERMES_AUTH_PATH"),
        os.path.expanduser(DEFAULT_HERMES_AUTH_PATH),
        os.path.expanduser("~/.config/hermes/auth.json"),  # some installs
    ])

    for raw_path in candidates:
        if not raw_path:
            continue
        path = Path(raw_path).expanduser()
        if not path.exists():
            continue

        try:
            data = json.loads(path.read_text())
        except Exception as e:
            logger.warning(f"Could not parse Hermes auth file {path}: {e}")
            continue

        token = _extract_xai_token(data)
        if token:
            masked = mask_token(token)
            logger.debug(
                f"Loaded xAI token from Hermes auth at {path} "
                f"(len={len(token)}, masked={masked})"
            )
            # Extra visibility for debugging "invalid key" errors
            logger.info(f"xAI token loaded (masked={masked}, len={len(token)})")
            return token

    raise RequestError(
        "No xAI Grok OAuth token found from Hermes. "
        "Run `hermes model` (or `hermes auth add xai-oauth`) in your Hermes environment, "
        "log in with your SuperGrok / X Premium+ account, and make sure `~/.hermes/auth.json` "
        "contains the xai-oauth credentials. "
        "You can also set HERMES_AUTH_PATH or hermes_auth_path in config."
    )


def _extract_xai_token(data: dict) -> Optional[str]:
    """Try multiple shapes in which Hermes may store the xai-oauth token.

    Supports the structure seen in practice:
    {
      "version": 1,
      "providers": {
        "xai-oauth": [
          {
            "id": "...",
            "access_token": "...",
            "refresh_token": "...",
            ...
          }
        ]
      }
    }
    """
    if not isinstance(data, dict):
        return None

    def _get_token_from_entry(entry: dict) -> Optional[str]:
        if not isinstance(entry, dict):
            return None
        # Check direct or under "tokens" (as Hermes stores in provider state)
        tok = (
            entry.get("access_token")
            or entry.get("token")
            or entry.get("bearer")
        )
        if tok:
            return tok
        tokens = entry.get("tokens")
        if isinstance(tokens, dict):
            return (
                tokens.get("access_token")
                or tokens.get("token")
                or tokens.get("bearer")
            )
        return None

    # Direct key at top level (rare)
    for key in ("xai-oauth", "xai", "grok-oauth"):
        entry = data.get(key)
        if isinstance(entry, dict):
            tok = _get_token_from_entry(entry)
            if tok:
                return tok
        elif isinstance(entry, list) and entry:
            # Take the first (usually the active one)
            tok = _get_token_from_entry(entry[0])
            if tok:
                return tok

    # Under "providers" (the structure provided by user)
    providers = data.get("providers") or {}
    if isinstance(providers, dict):
        for key in ("xai-oauth", "xai", "grok"):
            entry = providers.get(key)
            if isinstance(entry, dict):
                tok = _get_token_from_entry(entry)
                if tok:
                    return tok
            elif isinstance(entry, list) and entry:
                # Choose best candidate: prefer priority==0, then most recent last_refresh
                chosen = None
                best_refresh = ""
                for item in entry:
                    if not isinstance(item, dict):
                        continue
                    tok = _get_token_from_entry(item)
                    if not tok:
                        continue
                    if item.get("priority") == 0:
                        return tok  # highest priority wins immediately
                    refresh = item.get("last_refresh") or ""
                    if refresh > best_refresh:
                        best_refresh = refresh
                        chosen = item
                if chosen:
                    return _get_token_from_entry(chosen)
                # fallback to first valid
                for item in entry:
                    tok = _get_token_from_entry(item)
                    if tok:
                        return tok
            elif isinstance(entry, dict) and "tokens" in entry:
                # Sometimes providers.xai-oauth is a dict with tokens inside
                tok = _get_token_from_entry(entry)
                if tok:
                    return tok

    # Check credential_pool (another place Hermes stores xai-oauth entries)
    credential_pool = data.get("credential_pool") or {}
    if isinstance(credential_pool, dict):
        entries = credential_pool.get("xai-oauth") or credential_pool.get("xai") or []
        if isinstance(entries, list) and entries:
            for item in entries:
                tok = _get_token_from_entry(item)
                if tok:
                    return tok
        elif isinstance(entries, dict):
            tok = _get_token_from_entry(entries)
            if tok:
                return tok

    # Sometimes wrapped under "auth", "oauth", etc.
    for outer in ("auth", "oauth", "credentials"):
        sub = data.get(outer)
        if isinstance(sub, dict):
            tok = _extract_xai_token(sub)
            if tok:
                return tok

    # Last resort shallow scan (still useful for unknown layouts)
    def _scan(obj, depth=0):
        if depth > 5 or not isinstance(obj, (dict, list)):
            return None
        if isinstance(obj, dict):
            if "access_token" in obj:
                # Prefer entries that look xai/grok related
                if any(k in str(obj).lower() for k in ("xai", "grok", "oauth")) or any(
                    "xai" in str(k).lower() or "grok" in str(k).lower() for k in obj
                ):
                    return obj["access_token"]
                # fallback: any access_token
                return obj["access_token"]
            for v in obj.values():
                t = _scan(v, depth + 1)
                if t:
                    return t
        elif isinstance(obj, list):
            for item in obj:
                t = _scan(item, depth + 1)
                if t:
                    return t
        return None

    return _scan(data)