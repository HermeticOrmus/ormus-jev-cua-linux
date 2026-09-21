# Assay — ormus-jev-cua-linux

**Peer inspiration:** [shhivv/arc-cua](https://github.com/shhivv/arc-cua) (MIT, macOS AX + Apple Vision OCR)  
**This package:** Ormus Linux-first implementation with the same planner ↔ executor contracts  
**Assayed / built:** 2026-09-21  
**Claim hygiene:** Peer demo speed/cost claims are *theirs*. Do not restate arc-cua latency or dollar figures as Ormus results. Cite only owned logs from this box or approved hosts.

## What it is

Bounded desktop subtask execution for computer-use agents:

```text
planner → Subtask(goal, verification, inputs, constraints, max_actions)
       → DesktopExecutor: observe → Jev decide → freshness → execute → settle
       → SUBTASK_COMPLETE | BLOCKED | NEEDS_AGENT
```

Jev never invents literal text; `TYPE_TEXT` / `SET_VALUE` resolve `input_key` from `Subtask.inputs`.

## Platform

| Peer (arc-cua) | This package |
|---|---|
| macOS Accessibility (AX) | Linux AT-SPI2 via PyGObject `gi.repository.Atspi` |
| Apple Vision OCR | **Stub only** (`LinuxOcrProvider`) — Tesseract later |
| Click via AXPress | AT-SPI `do_action` or xdotool bounds-center fallback |
| dry_run not primary | **`dry_run=True` default** on live AT-SPI |

## Gold Hat

- **dry_run default True** for `LinuxAtspiBackend` — observe freely; skip mutations until a human Approves live UI on that host.
- **Never invent confidence** — TypeSafe returns confidence; backends do not fabricate it.
- **Human Approve for irreversible UI** (send / pay / delete / customer-facing) is **documented, not enforced in code**. Wire an Ormus decision-gate / Approve lane at the planner boundary.
- **No API keys in files** — `TYPESAFE_API_KEY` from the environment only.

## Setup notes (this box)

```bash
sudo apt-get install -y python3-gi gir1.2-atspi-2.0 python3-pyatspi at-spi2-core xdotool
cd /workspace/ormus/jev-cua-linux
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e '.[dev]'
```

`--system-site-packages` is required so `from gi.repository import Atspi` resolves from apt `python3-gi`.

## Dogfood status

- Memory backend + ScriptedPolicy: deterministic demo / pytest (no desktop needed).
- AT-SPI probe: exit 0 with SKIP when the accessibility bus has no registered apps (common on headless / sparse desktops).
- Live TypeSafe: optional; needs `TYPESAFE_API_KEY`.

## Not done in v0

- Tesseract OCR hybrid perception
- Wayland-native input (X11/xdotool path first)
- Enforcing Approve gates inside the executor
