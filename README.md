# ClawEar

A local audio capture + MCP server combo for conversational AI workflows.

- **`clawear`** — a CLI that records from a microphone, streams PCM audio to OpenAI Realtime, and writes a session triple to `~/ClawEar`:
  - `transcripts/<session_id>.md` — YAML frontmatter + dialog
  - `recordings/<session_id>.wav` — 16 kHz mono PCM
  - `events/<session_id>.jsonl` — OpenAI Realtime event stream
- **`clawear-mcp`** — an MCP server that indexes the above and exposes session navigation, FTS5 transcript search, event summaries, and WAV metadata to MCP clients (Claude Desktop, Claude Code, Codex, etc.).

Session ids use local-time format: `YYYY-MM-DD_HH-MM-SS` (e.g. `2026-04-21_14-12-39`). Frontmatter carries the unambiguous ISO 8601 `started_at` with timezone offset.

## Install

```bash
git clone <this-repo>
cd ClawEar
uv sync
```

This installs two console scripts into `.venv/bin/`:

- `clawear` — record
- `clawear-mcp` — serve

## Record with `clawear`

See `src/ear/cli.py` for arguments. A `.env` with `OPENAI_API_KEY` is expected.

```bash
uv run --env-file .env clawear
```

Files land in `$CLAWEAR_DATA_ROOT` (default `~/ClawEar`).

## Serve with `clawear-mcp`

Set `CLAWEAR_DATA_ROOT` and run:

```bash
CLAWEAR_DATA_ROOT=~/ClawEar uv run clawear-mcp
```

The server speaks MCP over stdio — register it in your client.

### Claude Desktop

macOS: edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "clawear": {
      "command": "/absolute/path/to/ClawEar/.venv/bin/clawear-mcp",
      "args": [],
      "env": {
        "CLAWEAR_DATA_ROOT": "/Users/you/ClawEar"
      }
    }
  }
}
```

Restart Claude Desktop.

### Claude Code

Add to `~/.claude/mcp_config.json` (or the project-local equivalent) using the same JSON shape.

### Codex

Follow your Codex client's MCP-server registration docs with the same command + env block.

## Tool reference

| Tool | Purpose |
|------|---------|
| `list_sessions(since?, until?, limit=50)` | List sessions, newest first, optionally bounded by `started_at` |
| `get_session(session_id)` | Frontmatter fields + computed stats (duration, event count) |
| `get_transcript(session_id, include_frontmatter=False)` | The markdown body |
| `search_transcripts(query, since?, until?, limit=10, snippet_tokens=32)` | FTS5 full-text search with snippets |
| `get_event_summary(session_id)` | Counts by event type + curated timeline + errors |
| `get_events(session_id, types?, item_id?, limit=200, offset=0)` | Raw events with filters + pagination |
| `get_recording_info(session_id)` | WAV metadata (duration, rate, channels, bit depth) |

## Resource URIs

| URI | MIME | Content |
|-----|------|---------|
| `clawear://transcript/<session_id>` | `text/markdown` | The `.md` file |
| `clawear://events/<session_id>` | `application/jsonl` | The `.jsonl` file |
| `clawear://recording/<session_id>` | `audio/wav` | The `.wav` bytes |

## Migrating existing sessions

If you have sessions recorded under the old UTC format (`...T04-12-39Z`), run the one-shot rename:

```bash
cd ClawEar
uv run python -m scripts.migrate_timestamps --dry-run  # preview
uv run python -m scripts.migrate_timestamps            # apply
```

The script is idempotent — already-migrated sessions are detected and skipped.

## Development

```bash
uv run pytest tests -v                  # full suite
uv run pytest tests/clawear_mcp -v      # just the MCP module
uv run pytest tests/ear -v              # just the recording CLI
```
