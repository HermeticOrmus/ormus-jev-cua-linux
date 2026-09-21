from __future__ import annotations

from ormus_jev_cua import ActionKind, Decision, DesktopElement, DesktopExecutor, DesktopSnapshot, Subtask, TerminalKind
from ormus_jev_cua.backends import StateMachineBackend
from ormus_jev_cua.policies import ScriptedPolicy


def snapshot(state: dict) -> DesktopSnapshot:
    elements = [
        DesktopElement(
            id="search",
            role="text_field",
            name="Search",
            value=state["value"],
            actions=(ActionKind.TYPE_TEXT,),
            source="test",
        )
    ]
    return DesktopSnapshot(
        application="Test App",
        window="Main",
        revision=state["value"],
        elements=tuple(elements),
    )


def transition(state: dict, action) -> None:
    if action.kind == ActionKind.TYPE_TEXT:
        state["value"] = action.value


def test_agent_supplied_text_is_materialized() -> None:
    backend = StateMachineBackend({"value": ""}, snapshot, transition)
    policy = ScriptedPolicy(
        [
            Decision(kind=ActionKind.TYPE_TEXT, target_id="search", input_key="query"),
            Decision(terminal=TerminalKind.SUBTASK_COMPLETE),
        ]
    )
    task = Subtask(
        goal="Search for Gaussian Blur",
        verification=("Search contains Gaussian Blur",),
        inputs={"query": "Gaussian Blur"},
    )

    result = DesktopExecutor(backend, policy).run(task)
    assert result.status == TerminalKind.SUBTASK_COMPLETE
    assert result.final_snapshot.element("search").value == "Gaussian Blur"
    assert result.history[0].action.value == "Gaussian Blur"


def test_no_change_loop_is_blocked() -> None:
    def no_op(state: dict, action) -> None:
        pass

    backend = StateMachineBackend({"value": ""}, snapshot, no_op)
    policy = ScriptedPolicy(
        [Decision(kind=ActionKind.TYPE_TEXT, target_id="search", input_key="query") for _ in range(3)]
    )
    task = Subtask(
        goal="Search",
        verification=("Search contains x",),
        inputs={"query": "x"},
    )

    result = DesktopExecutor(backend, policy).run(task)
    assert result.status == TerminalKind.BLOCKED
    assert result.actions_taken == 3


def test_atspi_backend_skips_without_desktop() -> None:
    """AT-SPI tests skip cleanly when no accessible apps are registered."""
    import pytest

    try:
        from ormus_jev_cua.backends.linux_atspi import LinuxAtspiBackend, atspi_available
    except Exception:
        pytest.skip("linux_atspi import failed")

    if not atspi_available():
        pytest.skip("AT-SPI not available")

    backend = LinuxAtspiBackend(dry_run=True)
    snap = backend.observe()
    assert snap.context.get("backend") == "linux_atspi"
    assert snap.context.get("dry_run") is True
    # Empty desktop is OK — just ensure observe does not raise
    assert isinstance(snap.elements, tuple)
