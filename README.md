# ormus-jev-cua-linux

**Linux AT-SPI action layer for Ormus Jev computer-use agents.**

Inspired by [shhivv/arc-cua](https://github.com/shhivv/arc-cua) (MIT) — same planner ↔ executor contracts, Linux-first perception via AT-SPI2 instead of macOS Accessibility + Apple Vision OCR.

> Peer speed/cost claims are not restated here. Measure on your own hosts.

---

A planner (any LLM or deterministic code) emits a bounded `Subtask`. This package loops observe → legal action space → **Jev** decision → execute → UI settle until `SUBTASK_COMPLETE` / `BLOCKED` / `NEEDS_AGENT`.

```python
from ormus_jev_cua import execute_payload

result = execute_payload(executor, {
    "goal": "Apply Gaussian Blur to the selected clip",
    "inputs": {"effect_name": "Gaussian Blur"},
    "verification": ["The selected clip has Gaussian Blur applied"],
    "constraints": ["Do not modify any other clip"],
    "max_actions": 10,
})
# {"status": "SUBTASK_COMPLETE", "actions_taken": 3, ...}
```

---

## Architecture

```text
planner / LLM
     ↓
Subtask(goal, verification, inputs, constraints, max_actions)
     ↓
DesktopExecutor
  observe → DecisionPolicy.decide → is_fresh → execute → settle
     ↓
SUBTASK_COMPLETE | BLOCKED | NEEDS_AGENT
```

| Piece | Role |
|---|---|
| `DesktopBackend` | `observe()` / `is_fresh()` / `execute()` |
| `DecisionPolicy` | `decide()` → `Decision` (action or terminal) |
| `StateMachineBackend` | In-memory demos/tests |
| `LinuxAtspiBackend` | Live AT-SPI2 (+ xdotool fallback) |
| `LinuxOcrProvider` | **Stub** (Tesseract later) |
| `ScriptedPolicy` | Deterministic stand-in for Jev |
| `TypeSafeJevPolicy` | Live Jev via TypeSafe SystemOne |

**Contracts:** Jev never invents literal text. `TYPE_TEXT` / `SET_VALUE` use `input_key` from `Subtask.inputs`. Terminals are only `SUBTASK_COMPLETE`, `BLOCKED`, `NEEDS_AGENT`.

---

## vs macOS arc-cua

| | arc-cua | ormus-jev-cua-linux |
|---|---|---|
| Perception | AX + Apple Vision OCR | AT-SPI2 (+ OCR stub) |
| Input | AX actions / CGEvent | AT-SPI `do_action` / xdotool |
| Default dry_run | — | **True** on AT-SPI |
| Package | `arc_cua` | `ormus_jev_cua` |

API parity: `subtask_from_dict`, `result_to_dict`, `execute_payload`, same `ActionKind` / models.

---

## Install (Linux)

Prefer **apt** for GI / AT-SPI (not pip):

```bash
sudo apt-get install -y python3-gi gir1.2-atspi-2.0 python3-pyatspi at-spi2-core xdotool

cd /workspace/ormus/jev-cua-linux
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

`--system-site-packages` lets the venv see system `gi` / Atspi.

### Live Jev (optional)

```bash
export TYPESAFE_API_KEY=...   # never commit keys
python examples/typesafe_smoke.py
```

---

## Gold Hat

- **`LinuxAtspiBackend(dry_run=True)` by default** — observations only; set `dry_run=False` only after human Approve for that host/session.
- **Never invent confidence** in backends or demos.
- **Irreversible UI** (send / pay / delete / customer-facing): document human Approve at the planner/decision-gate; **not enforced inside this package**.
- See [ASSAY.md](ASSAY.md).

---

## Examples

```bash
# Deterministic architecture demo (no API key, no desktop)
python examples/effects_demo.py

# AT-SPI tree probe (exit 0 + SKIP if no bus/apps)
python examples/atspi_probe.py

# Optional TypeSafe smoke
python examples/typesafe_smoke.py
```

---

## Tests

```bash
pytest -q
```

Memory-backend tests always run. AT-SPI cases skip cleanly when the accessibility desktop has no apps.

---

## License

MIT. Contract shapes inspired by arc-cua (MIT); this is an Ormus Linux implementation, not a git fork of that repository.
