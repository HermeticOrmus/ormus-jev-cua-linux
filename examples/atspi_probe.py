"""Probe the Linux AT-SPI tree. Exits 0 even when skipping (no bus / no apps)."""

from __future__ import annotations

import os
import sys


def main() -> int:
    display = os.environ.get("DISPLAY", "(unset)")
    print(f"DISPLAY={display}")

    try:
        from ormus_jev_cua.backends.linux_atspi import LinuxAtspiBackend, atspi_available
    except Exception as exc:
        print(f"SKIP: could not import LinuxAtspiBackend: {exc}")
        return 0

    if not atspi_available():
        print("SKIP: AT-SPI / PyGObject Atspi not available (install python3-gi gir1.2-atspi-2.0)")
        return 0

    try:
        backend = LinuxAtspiBackend(dry_run=True)
        snap = backend.observe()
    except Exception as exc:
        print(f"SKIP: observe failed: {exc}")
        return 0

    skip = snap.context.get("skip_reason")
    app_count = snap.context.get("app_count", "?")
    if skip or snap.application in {"(none)", ""} or not snap.elements:
        reason = skip or f"no accessible UI (app_count={app_count})"
        print(f"SKIP: {reason}")
        print(f"  application={snap.application!r} window={snap.window!r} elements={len(snap.elements)}")
        return 0

    print(f"application: {snap.application}")
    print(f"window: {snap.window}")
    print(f"revision: {snap.revision[:16]}...")
    print(f"elements: {len(snap.elements)} (dry_run={snap.context.get('dry_run')})")
    n = min(12, len(snap.elements))
    for el in snap.elements[:n]:
        acts = ",".join(a.value for a in el.actions) or "-"
        print(f"  [{el.id[:20]}] role={el.role!r} name={el.name!r} actions={acts}")
    if len(snap.elements) > n:
        print(f"  ... +{len(snap.elements) - n} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
