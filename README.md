# index01 — Pebble ring webhook receiver

Receives voice-note transcriptions from a [Pebble Index 01](https://repebble.com/index) smart ring and logs them to a markdown file. First stage of a pipeline that will eventually route notes into an Obsidian vault via Claude.

## How it works

```
ring → Cloudflare edge → tunnel (cloudflared) → localhost:7320
     → uvicorn → FastAPI (/inputs) → prepend to ring_log.md
```

The ring POSTs a `multipart/form-data` request on each recording. The webhook checks a bearer token, then prepends the transcription (with a Central-time timestamp) to the top of the log file so the newest note is always first.

## Files

- `ring_webhook_basic.py` — the FastAPI app
- `ring-webhook.service` — systemd unit (installed to `/etc/systemd/system/`)
- `ring-webhook.env` — auth token and config (**not committed** — see `.gitignore`)

## Setup

Install dependencies (system-wide, via apt):

```
sudo apt install python3-fastapi python3-uvicorn python3-multipart
```

Create `ring-webhook.env` with your token and lock it down:

```
echo "RING_AUTH_TOKEN=your-token-here" > ring-webhook.env
chmod 600 ring-webhook.env
```

Optional overrides in the same file: `RING_OUTPUT_FILE`, `RING_TZ`.

## Run

As a service (recommended):

```
sudo systemctl start ring-webhook.service
systemctl status ring-webhook.service
journalctl -u ring-webhook.service -f   # live logs
```

Or manually for testing:

```
RING_AUTH_TOKEN=... uvicorn ring_webhook_basic:app --host 127.0.0.1 --port 7320
```

## Ring configuration (Pebble app)

- **Webhook URL**: `https://ring.l13b.com/inputs`
- **Header**: `Authorization: Bearer <your-token>`
- **Send**: transcription (or both)

## Test

```
curl -X POST https://ring.l13b.com/inputs \
  -H "Authorization: Bearer your-token" \
  -F "transcription=test from curl" \
  -F "recordedAt=1754006400000" \
  -F "client=ring"
```

A successful call returns `{"status":"ok","saved":"test from curl",...}` and adds a line to the log.

## Endpoints

- `POST /inputs` — receives ring recordings (auth required)
- `GET /healthz` — health check, no auth

## Log format

Newest first, one markdown list item per note:

```
- 2026-08-01 16:12:15	Quick test of the Ring Talk.
```

## Roadmap

- Route notes into Obsidian by meaning (grocery items → `HEB.md`, tasks → daily note, etc.) via a Claude + Obsidian MCP call
- Persistent context across notes, with periodic compaction