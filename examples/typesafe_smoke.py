"""Optional live TypeSafe Jev smoke — requires TYPESAFE_API_KEY.

Does not send mutations unless you wire a non-dry_run backend yourself.
Default path uses StateMachineBackend + one decide() call only.
"""

from __future__ import annotations

import os
import sys

from ormus_jev_cua import ActionKind, DesktopElement, DesktopSnapshot, Subtask
from ormus_jev_cua.policies import TypeSafeJevPolicy


def main() -> int:
    if not os.environ.get("TYPESAFE_API_KEY"):
        print("SKIP: set TYPESAFE_API_KEY to run live Jev smoke")
        return 0

    snap = DesktopSnapshot(
        application="Smoke",
        window="Main",
        revision="1",
        elements=(
            DesktopElement(
                id="btn_ok",
                role="button",
                name="OK",
                actions=(ActionKind.CLICK,),
                source="smoke",
            ),
        ),
    )
    task = Subtask(
        goal="Click OK when ready",
        verification=("OK was clicked or dialog dismissed",),
        max_actions=3,
    )
    policy = TypeSafeJevPolicy()
    decision = policy.decide(subtask=task, snapshot=snap, history=[])
    print("decision:", decision)
    return 0


if __name__ == "__main__":
    sys.exit(main())
