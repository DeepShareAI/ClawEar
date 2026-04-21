# ble-mcp

A local macOS MCP server that exposes BLE scan / connect / read / write /
subscribe as tools to Claude Desktop, backed by `bleak`.

## Install (development)

Requires Python 3.11+ and `uv`.

```bash
uv sync --extra dev
uv run pytest
```

## Configure Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` and
add the entry from `claude_desktop_config.json.example` (edit the
`--directory` to point at your checkout). Restart Claude Desktop.

The first BLE op will trigger the macOS Bluetooth permission prompt against
the Claude Desktop process.

## Configure the server

Copy `config.example.toml` to `~/.config/ble-mcp/config.toml` and
edit. Supported keys:


| Key                        | Default  | Meaning                                                 |
| -------------------------- | -------- | ------------------------------------------------------- |
| `log_level`                | `"INFO"` | Python log level                                        |
| `scan_default_seconds`     | `5`      | Default scan duration                                   |
| `scan_max_seconds`         | `30`     | Max scan duration (caller is clamped)                   |
| `max_connections`          | `8`      | Max concurrent BLE connections                          |
| `notification_buffer_size` | `500`    | Ring-buffer size for pushed notifications               |
| `write_allowlist`          | `[]`     | Characteristic UUIDs that skip `confirm=True` on writes |


## Tools

- `ble_scan(duration_s=5, name_filter=None, rssi_min=None)`
- `ble_last_scan()`
- `ble_connect(address, timeout_s=10)`
- `ble_disconnect(address)`
- `ble_list_connections()`
- `ble_read(address, characteristic_uuid)`
- `ble_write(address, characteristic_uuid, data_hex, response=True, confirm=False)`
- `ble_subscribe(address, characteristic_uuid)`
- `ble_unsubscribe(address, characteristic_uuid)`
- `ble_notifications(address=None, since=None, limit=200)`

## Manual smoke test

1. Put a BLE heart-rate monitor (or any advertising BLE device) near your Mac.
2. In Claude Desktop: "Run ble_scan for 5 seconds and show what you found."
3. "Connect to  and read characteristic 00002a38-0000-1000-8000-00805f9b34fb."
4. "Subscribe to 00002a37-0000-1000-8000-00805f9b34fb and poll notifications for 30 seconds."

## Logs

Rotating logs at `~/Library/Logs/ble-mcp/server.log` (5MB × 5 files).
No characteristic payload bytes are logged — only address, UUID, and byte count.

---

# clawear

A companion CLI in this repo that records audio from the system's default input
(e.g., a connected Bluetooth headset) and streams it to OpenAI's Realtime API
while saving a local WAV and writing a Markdown transcript to a
JavisContext-MCP–watched directory.

## Install

```bash
uv sync --extra dev
```

## Configure

Copy `clawear.example.toml` to `~/.config/clawear/config.toml` and edit.
Important keys:

- `transcripts_dir` — must be inside a JavisContext `WATCH_DIRECTORIES` entry
for transcripts to auto-index.
- `recordings_dir`, `events_dir` — where the WAV and raw-events JSONL go.
- `instructions` — system prompt for the model; defaults to transcription +
passive notes.

Set your API key:

```bash
export OPENAI_API_KEY="sk-..."
```

## Manual smoke test

1. Pair + connect a Bluetooth Classic headset (AirPods, any HFP mic) via
  macOS Bluetooth preferences; select it as the input in Sound settings.
2. List visible inputs:
  ```bash
   uv run clawear list-devices
  ```
3. Preflight (no network):
  ```bash
   uv run clawear start --device "Javis" --dry-run
  ```
   Confirm the resolved device name and sample rate are correct.
4. Start a real session:
  ```bash
   uv run clawear start --device "Javis"
  ```
   Speak a few sentences. Include a topic shift, a name, and a decision.
5. Ctrl-C to stop.
6. Verify the three artifacts exist:
  ```bash
   ls -1 ~/ClawEar/recordings/*.wav \
         ~/Documents/knowledge-base/clawear/*.md \
         ~/ClawEar/events/*.jsonl
  ```
7. Open the latest `.md` in an editor; confirm the transcript and any
  `> note:` lines.
8. In Claude Desktop, ask JavisContext to `search_documents` for a phrase
  you spoke; confirm the MD is found.

## Logs

Rotating logs at `~/Library/Logs/clawear/clawear.log` (5MB × 5 files).
No audio bytes or transcript text are logged — only event types, sizes,
timings, device names, and error details.