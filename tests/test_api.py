from ormus_jev_cua import execute_payload, result_to_dict, subtask_from_dict
from ormus_jev_cua import ActionKind, Decision, DesktopElement, DesktopExecutor, DesktopSnapshot, Subtask, TerminalKind
from ormus_jev_cua.backends import StateMachineBackend
from ormus_jev_cua.policies import ScriptedPolicy


def test_json_boundary_requires_agent_verification() -> None:
    task = subtask_from_dict(
        {
            "goal": "Type a title",
            "verification": ["Title field contains Sydney 2026"],
            "inputs": {"title": "Sydney 2026"},
        }
    )
    assert task.inputs["title"] == "Sydney 2026"
    assert task.verification == ("Title field contains Sydney 2026",)


def test_execute_payload_roundtrip() -> None:
    def snapshot(state: dict) -> DesktopSnapshot:
        return DesktopSnapshot(
            application="App",
            window="W",
            revision=state["v"],
            elements=(
                DesktopElement(
                    id="b",
                    role="button",
                    name="Go",
                    actions=(ActionKind.CLICK,),
                    source="test",
                ),
            ),
        )

    def transition(state: dict, action) -> None:
        if action.kind == ActionKind.CLICK:
            state["v"] = "done"

    backend = StateMachineBackend({"v": "start"}, snapshot, transition)
    policy = ScriptedPolicy(
        [
            Decision(kind=ActionKind.CLICK, target_id="b"),
            Decision(terminal=TerminalKind.SUBTASK_COMPLETE),
        ]
    )
    out = execute_payload(
        DesktopExecutor(backend, policy),
        {
            "goal": "Click Go",
            "verification": ["Clicked"],
            "max_actions": 5,
        },
    )
    assert out["status"] == "SUBTASK_COMPLETE"
    assert out["actions_taken"] == 1
    assert "history" in out
