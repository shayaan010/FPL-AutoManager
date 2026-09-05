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

READ_TOKEN_JS = """(() => {
  const k = Object.keys(localStorage).find(k => k.startsWith('oidc.user:'));
  return k ? localStorage.getItem(k) : null;
})()"""


def _find_chrome() -> Optional[str]:
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
    if not PROFILE_DIR.exists():
        return
    for attempt in range(3):
        shutil.rmtree(PROFILE_DIR, ignore_errors=True)
        if not PROFILE_DIR.exists():
            return
        time.sleep(0.5)  
    logger.warning("Could not fully remove Chrome profile at %s", PROFILE_DIR)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _read_token_via_cdp(port: int) -> Optional[dict]:
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
                pass

            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            elapsed += POLL_INTERVAL_SECONDS

        raise TimeoutError("Timed out waiting for sign-in to complete")
    finally:
        if proc.poll() is None:
            proc.terminate()
