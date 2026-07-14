#!/usr/bin/env python3
"""
One-time helper to obtain a dedicated xAI OAuth token for dava.

Run this on the server (as the same user that runs the bot / systemd service):

    uv run scripts/init_xai_auth.py

It will:
  - Start a device-code login flow against auth.x.ai
  - Print a URL + code for you to approve in any browser
  - On approval, write access_token + refresh_token to the default location
    (~/.dava/xai_auth.json) or the path you specify via --auth-path

After this you can configure:

    image_generator=hermes
    video_generator=hermes
    # xai_auth_path=...   (only if you used a custom location)

This gives dava its own independent refresh grant, completely separate from
any Hermes Agent that may also be running on the machine.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Make sure we can import dava even when run directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dava.generators.xai_auth import perform_full_device_login_and_save


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Obtain a dedicated xAI OAuth token for the dava bot."
    )
    parser.add_argument(
        "--auth-path",
        dest="auth_path",
        default=None,
        help="Explicit path for the token file (default: ~/.dava/xai_auth.json)",
    )
    args = parser.parse_args()

    try:
        await perform_full_device_login_and_save(args.auth_path)
    except Exception as e:
        print(f"\n❌ Failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
