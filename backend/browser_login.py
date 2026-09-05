"""
FPL login via the user's own real Chrome.

FPL migrated auth to OAuth2/OIDC (PingOne at account.premierleague.com), and
the API is now authenticated with a **Bearer access token**, not session
cookies -- the old sessionid/pl_profile cookies no longer exist. The site's
SPA keeps its token bundle in localStorage under an "oidc.user:..." key and
patches window.fetch to attach `Authorization: Bearer <access_token>`.

Google also refuses to sign in inside an automated browser, so we don't
automate the login. We launch the user's real Chrome as an ordinary
subprocess -- no automation flags, nothing spoofed -- pointed at FPL. The
person signs in themselves. We only attach afterwards, over Chrome's own
debugging port, to read the token the site already stored.

The profile directory is persistent, so Chrome usually remembers the session
and later sign-ins are near-instant.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import httpx
import websockets

logger = logging.getLogger("browser_login")

START_URL = "https://fantasy.premierleague.com/"
POLL_INTERVAL_SECONDS = 1.0
TIMEOUT_SECONDS = 300

PROFILE_DIR = Path.home() / ".fpl-automanager" / "chrome-profile"

# Pulls the OIDC token bundle the FPL SPA stores after a successful login.
READ_TOKEN_JS = """(() => {
  const k = Object.keys(localStorage).find(k => k.startsWith('oidc.user:'));
  return k ? localStorage.getItem(k) : null;
})()"""


def _find_chrome() -> Optional[str]:
    """Locate the user's installed Chrome (or a Chromium-family equivalent)."""
    if sys.platform == "win32":
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        ]
    elif sys.platform == "darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
    else:
        candidates = []
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"):
            found = shutil.which(name)
            if found:
                candidates.append(found)

    for path in candidates:
        if path and Path(path).exists():
            return path
    return None


def clear_profile() -> None:
    """
    Wipe the persistent Chrome profile so the next sign-in starts logged out.

    Without this, "disconnect" only clears our own token -- Chrome stays signed
    into the previous FPL account and the next login silently reconnects to it,
    making it impossible to switch accounts.
    """
    if not PROFILE_DIR.exists():
        return
    for attempt in range(3):
        shutil.rmtree(PROFILE_DIR, ignore_errors=True)
        if not PROFILE_DIR.exists():
            return
        time.sleep(0.5)  # Chrome may still be releasing file locks
    logger.warning("Could not fully remove Chrome profile at %s", PROFILE_DIR)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _read_token_via_cdp(port: int) -> Optional[dict]:
    """Read the stored OIDC token bundle out of the FPL page, if it's there yet."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"http://127.0.0.1:{port}/json/list")
        resp.raise_for_status()
        targets = resp.json()

    page = next(
        (
            t
            for t in targets
            if t.get("type") == "page"
            and t.get("webSocketDebuggerUrl")
            and "premierleague.com" in (t.get("url") or "")
        ),
        None,
    )
    if not page:
        return None

    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=None) as ws:
        await ws.send(
            json.dumps(
                {
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {"expression": READ_TOKEN_JS, "returnByValue": True},
                }
            )
        )
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("id") == 1:
                raw = (msg.get("result", {}).get("result", {}) or {}).get("value")
                if not raw:
                    return None
                try:
                    bundle = json.loads(raw)
                except (TypeError, ValueError):
                    return None
                return bundle if bundle.get("access_token") else None


async def login_via_browser(fresh: bool = False) -> dict:
    """
    Open real Chrome, wait for the user to sign in, return the OIDC token bundle.

    fresh=True wipes the saved profile first, so the user gets a logged-out
    browser and can sign in as a different account.
    """
    chrome = _find_chrome()
    if not chrome:
        raise RuntimeError(
            "Couldn't find Chrome or Edge on this machine. Install Chrome, or use the "
            "manual token option."
        )

    if fresh:
        clear_profile()

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    port = _free_port()

    proc = subprocess.Popen(
        [
            chrome,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={PROFILE_DIR}",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            START_URL,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        elapsed = 0.0
        while elapsed < TIMEOUT_SECONDS:
            if proc.poll() is not None:
                raise RuntimeError("Login window was closed before signing in")

            try:
                bundle = await _read_token_via_cdp(port)
                if bundle:
                    return bundle
            except Exception:
                # Debug port not up yet, or no page target mid-redirect --
                # both expected while the user is still signing in.
                pass

            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            elapsed += POLL_INTERVAL_SECONDS

        raise TimeoutError("Timed out waiting for sign-in to complete")
    finally:
        if proc.poll() is None:
            proc.terminate()
