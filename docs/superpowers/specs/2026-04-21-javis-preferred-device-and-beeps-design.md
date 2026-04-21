# ClawEar — Javis preferred device routing & lifecycle beeps — design

**Date:** 2026-04-21
**Status:** Accepted (brainstorming complete)
**Repo:** `/Users/samuelwei/GoogleDrive/LLM/ClawEar`
**Related:** `docs/superpowers/specs/2026-04-20-clawear-audio-pipeline-design.md` (extends the capture layer), `docs/superpowers/specs/2026-04-21-clawear-transcription-only-session-design.md` (orthogonal — this spec does not change transcription behavior)

---

## 1. Scope & goal

Today, ClawEar opens the macOS CoreAudio **system default input** (unless `--device <x>` is passed) and has no audio output path. Users who want to record through a specific audio peripheral — in particular Javis, which presents to macOS as a regular CoreAudio input + output device (Bluetooth / USB / virtual driver) — must pass `--device javis` on every invocation, and receive no auditory feedback when recording starts, stops, or errors.

This spec adds two behaviors:

1. **Auto-prefer a device named "javis"** (case-insensitive substring) over the system default when `--device` is not passed. Silent fallback to the system default when no match is found.
2. **Lifecycle beeps** through the same Javis device — short start / stop / error tones generated in-code — so the user has confirmation that ClawEar is live on the right device without looking at the terminal.

Together these behaviors let ClawEar coexist with any other app that follows the macOS system default (Slack, WeChat, Zoom, WhatsApp, FaceTime, Spotify, browser-based meets, …) without contention: ClawEar routes exclusively through Javis, every other app keeps using whatever device it is bound to.

### Goals
- Zero-flag UX when Javis is present: `clawear` just works, recording + beeps on Javis.
- Graceful operation when Javis is absent: silent fallback to built-in, no stderr noise.
- No mutation of macOS system default audio state under any circumstance — explicit device-by-index opens only.
- Beep failures are warnings, never fatal — a dead beep channel must not abort a recording session.

### Out of scope
- TTS / conversational audio output. The 2026-04-21 transcription-only spec explicitly dropped conversational mode; this spec does not reverse that.
- Self-monitoring (mic playthrough to the speaker), replay of prior audio, or any output beyond the three lifecycle beeps.
- A configurable preferred-device name. `"javis"` is a module-level constant; making it a `Config` field is a trivial follow-up if ever needed.
- Mid-session device-switch / reconnect. If Javis disconnects while recording, we route through the existing capture-error path (exit 2).
- Bluetooth profile management. If Javis is a BT headset, macOS's A2DP↔HFP switch is a driver-layer side effect we document but do not mitigate.

---

## 2. Architecture

Two new behaviors, one new module, one function extended.

```
current:                         new:

┌───────────┐                    ┌───────────┐
│ session.py│                    │ session.py│──── calls player.beep_*() at
└─────┬─────┘                    └──┬─────┬──┘     lifecycle transitions
      │                             │     │
      ▼                             ▼     ▼
┌───────────┐                ┌──────────┐ ┌──────────┐
│ capture.py│                │capture.py│ │ output.py│  ← NEW module
└───────────┘                │ (input)  │ │ (beeps)  │
                             └──────────┘ └──────────┘
                                  │            │
                                  ▼            ▼
                           resolve_device / resolve_output_device
                           (share substring-preference rule)
```

### Invariants (hard rules)

1. ClawEar never mutates macOS global audio state. No `DefaultInput/OutputDevice` writes, no `osascript` device-flipping. Only `sounddevice.*Stream(device=<index>, …)` calls.
2. `--device <x>` always wins over auto-preference.
3. Every `BeepPlayer.beep_*()` and `.close()` call is self-wrapping: it catches `Exception`, logs at `WARNING`, and returns normally. Callers never need a `try/except` around a beep.
4. Preflight failures (before any stream is open) do not produce beeps — no device is resolved yet.

---

## 3. Components

### 3.1 `capture.resolve_device()` — extended (one function edit)

Public signature unchanged:

```python
def resolve_device(spec: str | None, devices: list[dict], default_input: int) -> dict
```

Behavior change, when `spec is None` only:

```
inputs = [d for d in devices if d.get("max_input_channels", 0) > 0]
preferred = _substring_match(_PREFERRED_DEVICE_SUBSTR, inputs)
if preferred is not None:
    return preferred
return devices[default_input]   # existing fallback
```

Module-level constant: `_PREFERRED_DEVICE_SUBSTR = "javis"`. Case-insensitive match (lowercase both sides). When multiple inputs match, pick the first (enumeration order is stable on macOS for a given device set).

### 3.2 `src/ear/output.py` — new module

Purpose: output-side device resolution and beep playback, kept fully separate from `capture.py` so the microphone-capture module stays single-purpose.

Public API:

```python
def resolve_output_device(
    devices: list[dict],
    default_output: int,
) -> dict

class BeepPlayer:
    def __init__(
        self,
        device: dict,
        output_stream_factory: Callable[..., Any] = _default_output_stream_factory,
    ): ...
    def beep_start(self) -> None
    def beep_stop(self)  -> None
    def beep_error(self) -> None
    def close(self)      -> None
```

`resolve_output_device` mirrors `resolve_device`'s no-spec branch but filters on `max_output_channels > 0` instead of input channels. `_PREFERRED_DEVICE_SUBSTR` is the same constant. No `spec` parameter — `--device` remains an **input-only** selector (unchanged CLI semantics); output always auto-prefers Javis or falls back to the system default. This avoids the surprise of `--device some_external_mic` silently rerouting beeps through a device the user chose only for recording.

### 3.3 Tone generation

In-code sine synthesis, no binary assets shipped. Uses `numpy` (already a ClawEar dep per `pyproject.toml`) to build an int16 PCM array, played via `sounddevice.OutputStream.write`.

| Beep | Tone | Duration | Envelope |
|---|---|---|---|
| `beep_start` | 700 Hz pure tone | 120 ms | sine, amp 0.2 of int16 full-scale (~6553) |
| `beep_stop`  | 500 Hz pure tone | 120 ms | sine, amp 0.2 |
| `beep_error` | three 800 Hz pulses of 60 ms each with 30 ms gaps | ~300 ms total | sine, amp 0.2 |

Sample rate is read from `output_device["default_samplerate"]` at `BeepPlayer.__init__`. No resampling path.

### 3.4 `session.py::run` — wiring (six edit points)

1. After `default_input_index` lookup, add the parallel `default_output_index` lookup (`sounddevice.default.device[1]`).
2. Resolve the output device and construct `BeepPlayer` alongside the existing `Capture` construction. Add `beep_player_factory: Callable[[dict], BeepPlayer] = _default_beep_player_factory` as a new injection parameter (mirrors `input_stream_factory`, `ws_factory` pattern).
3. Fire `player.beep_start()` once, after the `print("Recording from: …")` line and after `await client_obj.connect()` succeeds — i.e., only when we're actually live.
4. Fire `player.beep_stop()` in the clean-shutdown path, just before the final `print("wav: …")` output block.
5. Fire `player.beep_error()` on each error exit: capture-error (returns 2), ws-error (returns 3), fatal-exception (returns 5). Preflight failures (returns 1 / 5 before any stream opens) do **not** beep.
6. Call `player.close()` in the same positions that `wav.close()` / `evlog.close()` are called today.

### 3.5 `config.py` / `cli.py` — no changes

Auto-preference is hardcoded. `--device` already exists and still wins. No new TOML keys, no new CLI flags.

---

## 4. Data flow

### 4.1 Startup — device resolution

```
session.run() begins
    │
    ▼
sounddevice.query_devices() ─── enumerate CoreAudio devices
    │
    ▼
resolve_device(spec=args.device, devices, default_input_index)
    │    └── if spec given: substring-match spec (unchanged)
    │    └── if spec is None: try "javis" first, then fall back to default
    ▼
input_device = <resolved>
    │
    ▼
resolve_output_device(devices, default_output_index)
    │    (no spec; always auto-prefer "javis", else default output)
    ▼
output_device = <resolved>
    │
    ▼
input_stream_factory(device=input_device["index"], …)   ← capture opens
BeepPlayer(device=output_device)                         ← beep player opens
```

All stream opens use explicit `device=<index>`. macOS system default is read for fallback but never written.

### 4.2 Audio capture path (unchanged)

The full pipeline from `docs/superpowers/specs/2026-04-20-clawear-audio-pipeline-design.md` is untouched:

```
Javis mic → CoreAudio callback → capture.blocks queue
    ├── dispatcher → wav.append()           → WAV file
    └── dispatcher → realtime_queue → resampler → OpenAI Realtime WS
                                                       │
                                                       ▼
                                             event_consumer
                                                       │
                                                       ▼
                                         transcript.md + events.jsonl
```

Only the *physical device* changes — the pipeline downstream of the CoreAudio callback is bit-identical.

### 4.3 Beep output path (new)

```
session lifecycle event         BeepPlayer                       Javis speaker
─────────────────────           ──────────                       ─────────────
preflight OK + WS connect ──►   beep_start() ──► generate sine buffer (int16 PCM)
                                                  │
                                                  ▼
                                         OutputStream.write(buf)  ──► Javis spkr
                                         (blocks ~120ms, best-effort)

clean shutdown            ──►   beep_stop()  ──► same path
capture err (→ exit 2)    ──►   beep_error() ──► same path
ws err (→ exit 3)         ──►   beep_error() ──► same path
fatal exc (→ exit 5)      ──►   beep_error() ──► same path
```

Capture stream and beep stream are two independent `sounddevice.*Stream` objects. Sharing the same physical device (Javis) is handled natively by macOS — no custom mixing.

### 4.4 Coexistence with other apps

```
            ┌──── ClawEar audio thread ────┐ ┌──── output stream ────┐
ClawEar:    │ Javis mic → WAV + WS          │ │ beeps → Javis spkr   │
            └───────────────────────────────┘ └──────────────────────┘

            ┌──── Slack / WeChat / WhatsApp / ... audio thread ────┐
OtherApp:   │ built-in mic ↔ other-app ↔ built-in spkr               │
            └───────────────────────────────────────────────────────┘

macOS system default (untouched): built-in mic / built-in speakers
```

Every app holds its own stream handles bound to whatever device that app chose. ClawEar is invisible to other apps at the default-device layer because it never writes to it.

### 4.5 When Javis is absent at startup

```
query_devices() returns no "javis" substring match
    ▼
resolve_device fallback → devices[default_input_index]
resolve_output_device fallback → devices[default_output_index]
    ▼
ClawEar records from built-in mic; beeps play through built-in speakers
    ▼
No stderr warning. Session proceeds normally.
```

### 4.6 Mid-session Javis disconnect

Routed through the **existing** capture-error pipeline — no new code path:

- `sounddevice` callback receives a device-gone status
- `capture.error` future is set
- `session.py`'s `waitables` set wakes with `wait_capture_err in done`
- `capture_error_reason` is set, dispatcher drains, `transcript.set_truncated("capture error: …")`
- `player.beep_error()` attempted (will likely fail silently since output is also gone — that's fine)
- `player.close()` called, exit code 2 returned

No reconnect attempt, no retry loop. The existing truncation semantics apply.

---

## 5. Error handling

| Condition | Behavior | stderr | log level | Exit |
|---|---|---|---|---|
| Javis not present at startup (`spec is None`) | silent fallback to built-in for both I/O | — | debug | 0 |
| `--device <x>` with no match | raise `DeviceNotFoundError` (unchanged) | error message | error | 1 |
| `BeepPlayer.__init__` output stream open fails | swallow, log; subsequent `beep_*` calls are no-ops | — | warning | 0 |
| `beep_*` playback fails mid-play | swallow, log; that one beep skipped | — | warning | 0 |
| `BeepPlayer.close` raises | swallow, log | — | warning | 0 |
| Javis disconnects mid-session | existing capture-error path | error message | error | 2 |
| Two-index device collision (input-only vs output-only with same name) | each resolver filters by its own channel direction and matches independently | — | debug | 0 |
| Fatal exception in session | existing fatal-exc path; best-effort `beep_error` + `close` | existing | error | 5 |

Preflight failures before any stream is open (`DeviceNotFoundError` at preflight, other preflight exceptions) emit a minimal transcript and return exit 1 or 5 respectively — **no beep is played** because no output device is resolved yet.

---

## 6. Testing

Follows the existing fakes-based pattern in `tests/ear/` — all audio-device tests go through `fake_sounddevice.py` or an equivalent fake output stream.

### 6.1 `resolve_device()` preference (unit tests, extend `test_capture.py`)

| Test | Device list | `spec` | Default input | Expected |
|---|---|---|---|---|
| `test_resolve_prefers_javis_when_spec_is_none` | `[mbp_mic, Javis BT, external]` | `None` | `0` | returns `Javis BT` |
| `test_resolve_javis_match_is_case_insensitive` | `[mbp_mic, "javis earbuds"]` | `None` | `0` | returns `"javis earbuds"` |
| `test_resolve_falls_back_silently_when_no_javis` | `[mbp_mic, external]` | `None` | `0` | returns `mbp_mic`, stderr empty |
| `test_resolve_explicit_spec_overrides_javis` | `[mbp_mic, Javis BT, external]` | `"external"` | `0` | returns `external` |
| `test_resolve_explicit_spec_no_match_raises` | `[mbp_mic, Javis BT]` | `"foo"` | `0` | raises `DeviceNotFoundError` |
| `test_resolve_javis_filters_to_input_channels_only` | input-only Javis + output-only Javis, both matching substring | `None` | `0` | input resolver returns the input-only entry |

### 6.2 `resolve_output_device()` (new file `tests/ear/test_output.py`)

| Test | Scenario | Expected |
|---|---|---|
| `test_output_prefers_javis` | list includes Javis with output channels | returns Javis |
| `test_output_filters_input_only_devices` | Javis entry has `max_output_channels=0` | skip it, pick next output-capable |
| `test_output_falls_back_to_default` | no Javis with output | returns `devices[default_output]` |

### 6.3 `BeepPlayer` (unit tests, `tests/ear/test_output.py`)

Add `FakeOutputStream` to the test fakes:
- Records every `.write(buf)` call into a list (so tests can assert tone duration + non-empty buffer)
- Optional `.raise_on_write = Exception(...)` knob for negative-path tests
- `.close()` also inspectable

| Test | Expected |
|---|---|
| `test_beep_start_writes_nonempty_pcm` | after `beep_start()`, fake has one `.write` call with `len(buf) > 0` |
| `test_beep_start_duration_matches_spec` | buffer length / (2 bytes × sample_rate) ≈ 0.12 s ± 5% |
| `test_beep_error_writes_one_concatenated_buffer` | one write of the full concatenated three-pulse buffer (not three separate writes) |
| `test_beep_write_failure_is_swallowed` | fake raises on `.write()`; `player.beep_start()` does NOT propagate; log captures `"beep failed"` at WARNING |
| `test_beep_open_failure_is_swallowed` | `output_stream_factory` raises; player constructs; subsequent `beep_*` calls are no-ops + logged |
| `test_close_on_dead_stream_is_safe` | fake raises in `.close()`; `player.close()` does NOT propagate |
| `test_sample_rate_matches_output_device` | generated buffer length consistent with `device["default_samplerate"]`, not a hardcoded 48000 |

### 6.4 Session integration (extend `test_session.py`)

`session.run()` gains a new injection parameter:

```python
beep_player_factory: Callable[[dict], BeepPlayer] = _default_beep_player_factory
```

Tests inject a `FakeBeepPlayer` that records method calls in order:

| Test | Verifies |
|---|---|
| `test_happy_path_calls_beep_start_then_beep_stop` | `[beep_start, beep_stop, close]` in order |
| `test_capture_error_path_calls_beep_error` | capture fatal status → exit 2 → `[beep_start, beep_error, close]` |
| `test_ws_error_path_calls_beep_error` | WS drops mid-session → exit 3 → `[beep_start, beep_error, close]` |
| `test_preflight_failure_does_not_call_any_beep` | device-not-found at preflight → exit 1 → zero beep calls |
| `test_fatal_exception_calls_beep_error` | unhandled exception → exit 5 → `[beep_error, close]` (beep_start may or may not have fired depending on where the exception occurred) |

### 6.5 Manual smoke test (update README)

Add the Javis leg:

1. Pair Javis; confirm it appears in `clawear list-devices`.
2. Run `clawear` with no `--device` → "Recording from: Javis @ …" prints; start beep audible in Javis speaker.
3. While recording, open Slack / WhatsApp / any other audio app; verify it uses built-in mic + speaker (expected default), and ClawEar continues recording via Javis undisturbed.
4. Ctrl+C → stop beep audible in Javis speaker; transcript written to `~/ClawEar/transcripts/`.
5. Unpair Javis, re-run `clawear` → silent fallback to built-in; recording + beeps through MacBook speaker; no stderr warning.

### 6.6 What is NOT tested

- Real `sounddevice` / CoreAudio behavior — all tests use fakes. The fake is the contract.
- Bluetooth A2DP↔HFP profile switching — OS-level side effect, documented as a caveat (§7).
- Sample-rate resampling for beeps — we sidestep by reading the device's native rate.

---

## 7. Known caveats

### 7.1 Bluetooth profile switch

If Javis connects as a Bluetooth headset (HFP / Hands-Free Profile) rather than A2DP (one-way stereo), macOS may flip the Bluetooth link from A2DP to HFP when ClawEar opens the input stream. This is a driver-layer side effect outside ClawEar's control. Observable impact: any app that was playing stereo to Javis before ClawEar started (e.g., Spotify) may notice quality degradation. Does not affect system default or any other app's device binding. Mitigation (not implemented here): use a virtual loopback driver such as BlackHole or Loopback to decouple ClawEar's input from the BT profile.

### 7.2 Hardcoded substring

`_PREFERRED_DEVICE_SUBSTR = "javis"` is a module-level constant. Users who rename their Javis device to something that no longer contains "javis" will see the silent fallback behavior — ClawEar records on built-in as if Javis weren't present. Resolution: either don't rename, pass `--device <new-name>` explicitly, or file a follow-up to make the substring a `Config` field.

### 7.3 Ambiguity when multiple "javis" devices present

If the CoreAudio enumeration returns multiple devices matching the substring (e.g., an old paired entry and a new one both visible), the resolver picks the first in enumeration order. On macOS this order is stable for a given device set but is not user-controllable. User resolution: unpair stale entries, or pass `--device <exact-name>`.

---

## 8. File manifest

New:
- `ClawEar/src/ear/output.py` — `resolve_output_device`, `BeepPlayer`, `_default_output_stream_factory`, tone-generation helpers
- `ClawEar/tests/ear/test_output.py` — unit tests for resolver + BeepPlayer
- Extend `ClawEar/tests/ear/fake_sounddevice.py` with `FakeOutputStream`

Modified:
- `ClawEar/src/ear/capture.py` — extend `resolve_device` with the "javis" preference branch; add `_PREFERRED_DEVICE_SUBSTR` constant
- `ClawEar/src/ear/session.py` — resolve output device, construct BeepPlayer, wire `beep_start/stop/error` + `close` at the documented five edit points; add `beep_player_factory` injection parameter
- `ClawEar/tests/ear/test_capture.py` — new tests for preference logic (see §6.1)
- `ClawEar/tests/ear/test_session.py` — new tests for beep lifecycle (see §6.4)
- `ClawEar/README.md` — add Javis leg to manual smoke test (see §6.5)

Unchanged:
- `config.py`, `cli.py`, `resampler.py`, `transcript.py`, `wav_writer.py`, `events_log.py`, `realtime_client.py`, all existing tests not listed above.
