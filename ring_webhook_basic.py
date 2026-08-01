"""
Minimal webhook receiver for Pebble Index 01.

Receives the ring's multipart/form-data POST and prepends the transcription
(with its timestamp) to the TOP of a markdown log file, so the newest note
is always first. Nothing else yet -- no Claude, no vault writes.

Pebble webhook payload (multipart/form-data fields):
  - transcription : text of the note (present when set to send text/both)
  - audio         : audio/mp4 blob (present when set to send audio/both)
  - recordedAt    : recording time, ms since unix epoch (always)
  - client        : always the text 'ring'

Auth: Pebble lets you configure custom request headers. Set an
  Authorization: Bearer <token>
header on the ring side and put the same token in RING_AUTH_TOKEN here.

Run:
  pip install fastapi uvicorn python-multipart
  RING_AUTH_TOKEN=... uvicorn ring_webhook_basic:app --host 127.0.0.1 --port 7320
"""

import os
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Form, Header, HTTPException, UploadFile, File
from typing import Optional

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ring_webhook")

app = FastAPI()

# Shared secret you also configure as an Authorization header on the ring.
# Leave unset to skip the check while testing locally.
RING_AUTH_TOKEN = os.environ.get("RING_AUTH_TOKEN")

# Where transcripts land. Newest entries are prepended to the top.
OUTPUT_FILE = os.environ.get("RING_OUTPUT_FILE", "/home/cordoba/vaults/ring_log.md")

# Local timezone for rendering timestamps. America/Chicago handles CST/CDT
# (daylight saving) automatically.
LOCAL_TZ = ZoneInfo(os.environ.get("RING_TZ", "America/Chicago"))


def _fmt_recorded_at(recorded_at: Optional[str]) -> str:
    """recordedAt is ms since epoch; render it in local time, fall back to raw."""
    if not recorded_at:
        return "unknown-time"
    try:
        ts = int(recorded_at) / 1000
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(LOCAL_TZ)
        # e.g. "2025-08-01 09:30:15" (Central time)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return recorded_at


def prepend_entry(entry: str) -> None:
    """Write `entry` to the top of OUTPUT_FILE, preserving existing content."""
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    try:
        with open(OUTPUT_FILE, "r") as f:
            existing = f.read()
    except FileNotFoundError:
        existing = ""
    with open(OUTPUT_FILE, "w") as f:
        f.write(entry + existing)


@app.post("/inputs")
async def ring_webhook(
    transcription: Optional[str] = Form(default=None),
    recordedAt: Optional[str] = Form(default=None),
    client: Optional[str] = Form(default=None),
    audio: Optional[UploadFile] = File(default=None),
    authorization: Optional[str] = Header(default=None),
):
    # Simple bearer-token check
    if RING_AUTH_TOKEN:
        expected = f"Bearer {RING_AUTH_TOKEN}"
        if authorization != expected:
            raise HTTPException(status_code=401, detail="invalid or missing token")

    when = _fmt_recorded_at(recordedAt)

    if not transcription:
        # Could be an audio-only webhook, or transcription failed. Log and move on.
        log.info("Webhook received with no transcription (client=%s, when=%s)", client, when)
        return {"status": "ok", "note": "no transcription in payload"}

    # Markdown list item, newest on top: "- <timestamp> <text>"
    entry = f"- {when}\t{transcription.strip()}\n"
    prepend_entry(entry)

    log.info("Saved transcript (%s): %s", when, transcription.strip())
    return {"status": "ok", "saved": transcription.strip(), "recordedAt": when}


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}