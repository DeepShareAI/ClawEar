# ble-explorer-mcp

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

Copy `config.example.toml` to `~/.config/ble-explorer-mcp/config.toml` and
edit. Supported keys:

| Key | Default | Meaning |
| --- | --- | --- |
| `log_level` | `"INFO"` | Python log level |
| `scan_default_seconds` | `5` | Default scan duration |
| `scan_max_seconds` | `30` | Max scan duration (caller is clamped) |
| `max_connections` | `8` | Max concurrent BLE connections |
| `notification_buffer_size` | `500` | Ring-buffer size for pushed notifications |
| `write_allowlist` | `[]` | Characteristic UUIDs that skip `confirm=True` on writes |

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
3. "Connect to <address> and read characteristic 00002a38-0000-1000-8000-00805f9b34fb."
4. "Subscribe to 00002a37-0000-1000-8000-00805f9b34fb and poll notifications for 30 seconds."

## Logs

Rotating logs at `~/Library/Logs/ble-explorer-mcp/server.log` (5MB × 5 files).
No characteristic payload bytes are logged — only address, UUID, and byte count.
