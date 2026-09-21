"""Linux AT-SPI2 desktop backend via PyGObject Atspi.

Gold Hat: dry_run defaults to True — observe freely, skip mutations unless
explicitly enabled. Confidence is never invented here (perception has none).
Human Approve for irreversible UI (send/pay/delete) is documented, not enforced.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from typing import Any

from ..errors import StaleDesktopState, UnsupportedDesktopAction
from ..models import ActionKind, Bounds, DesktopElement, DesktopSnapshot, ExecutableAction

# Prefer apt packages: python3-gi, gir1.2-atspi-2.0, at-spi2-core
_ATSPI = None
_ATSPI_IMPORT_ERROR: Exception | None = None


def _load_atspi():
    global _ATSPI, _ATSPI_IMPORT_ERROR
    if _ATSPI is not None:
        return _ATSPI
    if _ATSPI_IMPORT_ERROR is not None:
        raise RuntimeError(
            f"AT-SPI unavailable: {_ATSPI_IMPORT_ERROR}. "
            "Install: sudo apt-get install -y python3-gi gir1.2-atspi-2.0 at-spi2-core"
        ) from _ATSPI_IMPORT_ERROR
    try:
        import gi

        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi

        Atspi.init()
        _ATSPI = Atspi
        return Atspi
    except Exception as exc:  # pragma: no cover
        _ATSPI_IMPORT_ERROR = exc
        raise RuntimeError(
            f"AT-SPI unavailable: {exc}. "
            "Install: sudo apt-get install -y python3-gi gir1.2-atspi-2.0 at-spi2-core"
        ) from exc


# Role name (lower) → ActionKind capabilities when AT-SPI actions are incomplete
_CLICK_ROLES = {
    "push button",
    "button",
    "toggle button",
    "check box",
    "radio button",
    "menu item",
    "menu",
    "link",
    "tab",
    "page tab",
    "list item",
    "tree item",
    "combo box",
    "image",
    "icon",
}
_TEXT_ROLES = {
    "text",
    "entry",
    "password text",
    "editable text",
    "terminal",
    "combo box",
    "spin button",
}
_VALUE_ROLES = _TEXT_ROLES | {"slider", "scrollbar", "spin button"}


def atspi_available() -> bool:
    try:
        _load_atspi()
        return True
    except Exception:
        return False


class LinuxAtspiBackend:
    """Semantic Linux desktop backend over AT-SPI2 (+ xdotool fallback).

    Parameters
    ----------
    dry_run:
        When True (default), observe() works but execute() records no mutations
        (skips AT-SPI do_action / xdotool). Prefer True until a human Approves
        live UI automation on a given host.
    application_name:
        Optional filter: prefer this app name when selecting the active tree root.
    """

    def __init__(
        self,
        *,
        dry_run: bool = True,
        max_elements: int = 1200,
        max_depth: int = 18,
        application_name: str | None = None,
        settle_s: float = 0.05,
    ) -> None:
        self.dry_run = dry_run
        self.max_elements = max_elements
        self.max_depth = max_depth
        self.application_name = application_name
        self.settle_s = settle_s
        self._refs: dict[str, Any] = {}
        self._xdotool = shutil.which("xdotool")
        _load_atspi()

    def observe(self) -> DesktopSnapshot:
        Atspi = _load_atspi()
        desktop = Atspi.get_desktop(0)
        app, window = self._select_root(desktop)
        if app is None:
            revision = hashlib.sha256(b"empty").hexdigest()
            self._refs = {}
            return DesktopSnapshot(
                application="(none)",
                window="(none)",
                revision=revision,
                elements=(),
                context={
                    "backend": "linux_atspi",
                    "dry_run": self.dry_run,
                    "app_count": int(desktop.get_child_count() or 0),
                    "skip_reason": "no accessible applications on AT-SPI desktop",
                },
                captured_at_ms=round(time.time() * 1000),
            )

        app_name = _safe_name(app) or self.application_name or "unknown"
        window_title = _safe_name(window) if window is not None else app_name
        root = window if window is not None else app

        refs: dict[str, Any] = {}
        elements: list[DesktopElement] = []
        visited: set[int] = set()
        self._walk(root, elements, refs, visited, parent_id=None, depth=0)
        self._refs = refs

        revision_payload = [
            {
                "id": e.id,
                "role": e.role,
                "name": e.name,
                "value": e.value,
                "enabled": e.enabled,
                "focused": e.focused,
                "selected": e.selected,
                "expanded": e.expanded,
                "parent_id": e.parent_id,
            }
            for e in elements
        ]
        revision = hashlib.sha256(
            json.dumps(revision_payload, sort_keys=True, default=str).encode()
        ).hexdigest()
        return DesktopSnapshot(
            application=app_name,
            window=window_title or app_name,
            revision=revision,
            elements=tuple(elements),
            context={
                "backend": "linux_atspi",
                "dry_run": self.dry_run,
                "app_count": int(desktop.get_child_count() or 0),
                "element_count": len(elements),
            },
            captured_at_ms=round(time.time() * 1000),
        )

    def is_fresh(self, snapshot: DesktopSnapshot, action: ExecutableAction) -> bool:
        if action.target_id:
            ref = self._refs.get(action.target_id)
            if ref is None:
                return False
            try:
                expected = snapshot.element(action.target_id)
            except KeyError:
                return False
            current = self._element_from_accessible(
                ref, action.target_id, parent_id=expected.parent_id
            )
            if current is None or current.semantic_guard() != action.target_guard:
                return False
        if action.secondary_target_id:
            ref = self._refs.get(action.secondary_target_id)
            if ref is None:
                return False
            try:
                expected = snapshot.element(action.secondary_target_id)
            except KeyError:
                return False
            current = self._element_from_accessible(
                ref, action.secondary_target_id, parent_id=expected.parent_id
            )
            if current is None or current.semantic_guard() != action.secondary_target_guard:
                return False
        return True

    def execute(self, snapshot: DesktopSnapshot, action: ExecutableAction) -> None:
        if not self.is_fresh(snapshot, action):
            raise StaleDesktopState("AT-SPI target changed before execution")

        if action.kind == ActionKind.WAIT:
            if not self.dry_run:
                time.sleep(0.1)
            return

        if action.kind == ActionKind.PRESS_KEY:
            self._press_key(action.key or "")
            return
        if action.kind == ActionKind.HOTKEY:
            self._press_hotkey(action.hotkey or "")
            return
        if action.kind == ActionKind.SCROLL:
            self._scroll(action.scroll_direction or "DOWN")
            return

        if not action.target_id:
            raise UnsupportedDesktopAction(f"{action.kind.value} requires a target on Linux AT-SPI")
        ref = self._refs.get(action.target_id)
        if ref is None:
            raise StaleDesktopState("Target no longer exists")

        if action.kind in {ActionKind.CLICK, ActionKind.DOUBLE_CLICK, ActionKind.RIGHT_CLICK}:
            self._click(ref, snapshot.element(action.target_id), action.kind)
            return

        if action.kind in {ActionKind.TYPE_TEXT, ActionKind.SET_VALUE}:
            if action.value is None:
                raise UnsupportedDesktopAction(f"{action.kind.value} requires an agent-supplied value")
            self._type_or_set(ref, snapshot.element(action.target_id), action)
            return

        if action.kind in {ActionKind.DRAG_TO, ActionKind.DRAG_BY}:
            raise UnsupportedDesktopAction(f"LinuxAtspiBackend v0 cannot execute {action.kind.value}")

        raise UnsupportedDesktopAction(f"LinuxAtspiBackend v0 cannot execute {action.kind.value}")

    # --- tree selection / walk -------------------------------------------------

    def _select_root(self, desktop: Any) -> tuple[Any | None, Any | None]:
        count = int(desktop.get_child_count() or 0)
        preferred = (self.application_name or "").strip().lower()
        apps: list[Any] = []
        for i in range(count):
            try:
                app = desktop.get_child_at_index(i)
            except Exception:
                continue
            if app is None:
                continue
            apps.append(app)

        if preferred:
            for app in apps:
                if preferred in (_safe_name(app) or "").lower():
                    return app, self._first_window(app)

        # Prefer an app that has at least one window-like child
        for app in apps:
            win = self._first_window(app)
            if win is not None:
                return app, win

        if apps:
            return apps[0], self._first_window(apps[0])
        return None, None

    def _first_window(self, app: Any) -> Any | None:
        try:
            n = int(app.get_child_count() or 0)
        except Exception:
            return None
        for i in range(n):
            try:
                child = app.get_child_at_index(i)
            except Exception:
                continue
            if child is None:
                continue
            role = (_safe_role(child) or "").lower()
            if role in {"frame", "window", "dialog", "file chooser", "alert"}:
                return child
        # Fall back to first child
        if n > 0:
            try:
                return app.get_child_at_index(0)
            except Exception:
                return None
        return None

    def _walk(
        self,
        accessible: Any,
        elements: list[DesktopElement],
        refs: dict[str, Any],
        visited: set[int],
        *,
        parent_id: str | None,
        depth: int,
    ) -> None:
        if depth > self.max_depth or len(elements) >= self.max_elements:
            return
        try:
            key = id(accessible)
        except Exception:
            return
        if key in visited:
            return
        visited.add(key)

        element_id = _stable_id(accessible)
        element = self._element_from_accessible(accessible, element_id, parent_id=parent_id)
        next_parent = parent_id
        if element is not None:
            elements.append(element)
            refs[element.id] = accessible
            next_parent = element.id

        try:
            n = int(accessible.get_child_count() or 0)
        except Exception:
            return
        for i in range(n):
            if len(elements) >= self.max_elements:
                break
            try:
                child = accessible.get_child_at_index(i)
            except Exception:
                continue
            if child is None:
                continue
            self._walk(
                child,
                elements,
                refs,
                visited,
                parent_id=next_parent,
                depth=depth + 1,
            )

    def _element_from_accessible(
        self,
        accessible: Any,
        element_id: str,
        *,
        parent_id: str | None,
    ) -> DesktopElement | None:
        role = _safe_role(accessible)
        if not role:
            return None
        name = _safe_name(accessible) or ""
        value = _safe_value(accessible)
        states = _state_set(accessible)
        # AT-SPI often uses STATE_ENABLED / STATE_SENSITIVE
        enabled = any(s.lower() in {"enabled", "sensitive"} for s in states) or (
            not any(s.lower() in {"disabled", "defunct"} for s in states)
        )
        visible = not any(s.lower() in {"invisible", "defunct"} for s in states)
        focused = any(s.lower() == "focused" for s in states)
        selected = True if any(s.lower() == "selected" for s in states) else None
        expanded = True if any(s.lower() == "expanded" for s in states) else (
            False if any(s.lower() == "collapsed" for s in states) else None
        )
        bounds = _bounds(accessible)
        action_names = _action_names(accessible)
        capabilities = _map_actions(role, action_names, states)

        # Skip barren structural nodes with no name/actions unless focused
        role_l = role.lower()
        if (
            not name
            and not capabilities
            and role_l in {"filler", "panel", "section", "separator", "scroll pane", "viewport"}
            and not focused
        ):
            return None

        return DesktopElement(
            id=element_id,
            role=role,
            name=name,
            value=value,
            actions=tuple(capabilities),
            enabled=enabled,
            visible=visible,
            focused=focused,
            selected=selected,
            expanded=expanded,
            parent_id=parent_id,
            bounds=bounds,
            source="linux_atspi",
            accepts_drop=any(s.lower() == "droppable" for s in states),
            metadata={"atspi_actions": action_names} if action_names else {},
        )

    # --- mutations -------------------------------------------------------------

    def _click(self, ref: Any, element: DesktopElement, kind: ActionKind) -> None:
        if self.dry_run:
            return
        names = _action_names(ref)
        preferred = None
        if kind == ActionKind.CLICK:
            for candidate in ("click", "press", "activate", "Jump"):
                for n in names:
                    if n.lower() == candidate.lower():
                        preferred = n
                        break
                if preferred:
                    break
            if preferred is None and names:
                preferred = names[0]
        elif kind == ActionKind.RIGHT_CLICK:
            for n in names:
                if "menu" in n.lower() or "context" in n.lower():
                    preferred = n
                    break
        # DOUBLE_CLICK / RIGHT_CLICK often need coordinate fallback

        if preferred is not None and kind == ActionKind.CLICK:
            if _do_action(ref, preferred):
                time.sleep(self.settle_s)
                return

        # Fallback: xdotool at bounds center
        if element.bounds is None:
            raise UnsupportedDesktopAction("No AT-SPI action and no bounds for click fallback")
        self._xdotool_click(element.bounds, kind)

    def _type_or_set(self, ref: Any, element: DesktopElement, action: ExecutableAction) -> None:
        if self.dry_run:
            return
        # Focus first
        focused = False
        for n in _action_names(ref):
            if n.lower() in {"focus", "grabfocus", "click", "press"}:
                if _do_action(ref, n):
                    focused = True
                    break
        if not focused and element.bounds is not None:
            self._xdotool_click(element.bounds, ActionKind.CLICK)

        text = str(action.value)
        # Prefer set text when interface available
        if action.kind == ActionKind.SET_VALUE:
            if _try_set_text(ref, text):
                return
        # TYPE_TEXT: clear + type via xdotool (or set_text then done)
        if _try_set_text(ref, text) and action.kind == ActionKind.SET_VALUE:
            return
        if action.kind == ActionKind.TYPE_TEXT:
            # Replace: select-all then type
            self._press_hotkey("MOD+A")
            time.sleep(0.05)
            self._xdotool_type(text)
            return
        # SET_VALUE fallback
        self._press_hotkey("MOD+A")
        time.sleep(0.05)
        self._xdotool_type(text)

    def _press_key(self, key: str) -> None:
        if self.dry_run:
            return
        mapping = {
            "ENTER": "Return",
            "ESCAPE": "Escape",
            "TAB": "Tab",
            "SPACE": "space",
            "BACKSPACE": "BackSpace",
            "DELETE": "Delete",
            "ARROW_UP": "Up",
            "ARROW_DOWN": "Down",
            "ARROW_LEFT": "Left",
            "ARROW_RIGHT": "Right",
        }
        xkey = mapping.get(key.upper(), key)
        self._run_xdotool(["key", xkey])

    def _press_hotkey(self, hotkey: str) -> None:
        if self.dry_run:
            return
        # MOD → ctrl on Linux
        parts = [p.strip() for p in hotkey.replace("MOD", "ctrl").split("+") if p.strip()]
        bits = []
        for p in parts:
            pl = p.lower()
            if pl in {"ctrl", "control"}:
                bits.append("ctrl")
            elif pl in {"alt", "shift", "super", "meta"}:
                bits.append(pl)
            elif pl == "mod":
                bits.append("ctrl")
            else:
                bits.append(p)
        self._run_xdotool(["key", "+".join(bits)])

    def _scroll(self, direction: str) -> None:
        if self.dry_run:
            return
        # xdotool click 4/5 for up/down; left/right less portable
        button = {"UP": "4", "DOWN": "5", "LEFT": "6", "RIGHT": "7"}.get(direction.upper(), "5")
        self._run_xdotool(["click", button])

    def _xdotool_click(self, bounds: Bounds, kind: ActionKind) -> None:
        cx, cy = bounds.center
        x, y = int(cx), int(cy)
        if kind == ActionKind.DOUBLE_CLICK:
            self._run_xdotool(["mousemove", "--sync", str(x), str(y), "click", "--repeat", "2", "1"])
        elif kind == ActionKind.RIGHT_CLICK:
            self._run_xdotool(["mousemove", "--sync", str(x), str(y), "click", "3"])
        else:
            self._run_xdotool(["mousemove", "--sync", str(x), str(y), "click", "1"])
        time.sleep(self.settle_s)

    def _xdotool_type(self, text: str) -> None:
        # --clearmodifiers avoids sticky modifiers from prior hotkeys
        self._run_xdotool(["type", "--clearmodifiers", "--", text])

    def _run_xdotool(self, args: list[str]) -> None:
        if not self._xdotool:
            raise UnsupportedDesktopAction("xdotool not found on PATH")
        env = os.environ.copy()
        # Preserve DISPLAY for the caller's session
        try:
            subprocess.run(
                [self._xdotool, *args],
                check=True,
                env=env,
                capture_output=True,
                timeout=10,
            )
        except subprocess.CalledProcessError as exc:
            raise UnsupportedDesktopAction(
                f"xdotool failed: {exc.stderr.decode(errors='replace')[:200]}"
            ) from exc


# --- helpers ------------------------------------------------------------------


def _safe_name(accessible: Any) -> str:
    try:
        name = accessible.get_name()
        return str(name) if name else ""
    except Exception:
        return ""


def _safe_role(accessible: Any) -> str:
    try:
        role = accessible.get_role_name()
        if role:
            return str(role)
    except Exception:
        pass
    try:
        role = accessible.get_role()
        return str(role).replace("ATSPI_ROLE_", "").replace("_", " ").title()
    except Exception:
        return ""


def _safe_value(accessible: Any) -> str | int | float | bool | None:
    try:
        text = accessible.get_text(0, -1)
        if text is not None and str(text) != "":
            return str(text)
    except Exception:
        pass
    try:
        iface = accessible.get_value_iface()
        if iface is not None:
            return float(iface.get_current_value())
    except Exception:
        pass
    return None


def _state_set(accessible: Any) -> list[str]:
    try:
        states = accessible.get_state_set()
        if states is None:
            return []
        # PyGObject: get_states() returns list of Atspi.StateType
        try:
            raw = states.get_states()
            return [str(s).split("_")[-1].lower() for s in raw]
        except Exception:
            out = []
            for name in (
                "ENABLED",
                "SENSITIVE",
                "VISIBLE",
                "SHOWING",
                "FOCUSED",
                "SELECTED",
                "EXPANDED",
                "COLLAPSED",
                "EDITABLE",
                "FOCUSABLE",
                "ACTIVE",
                "DEFUNCT",
                "INVISIBLE",
            ):
                try:
                    from gi.repository import Atspi

                    st = getattr(Atspi.StateType, name, None)
                    if st is not None and states.contains(st):
                        out.append(name.lower())
                except Exception:
                    continue
            return out
    except Exception:
        return []


def _action_names(accessible: Any) -> list[str]:
    try:
        action = accessible.get_action_iface()
        if action is None:
            return []
        n = int(action.get_n_actions() or 0)
        names = []
        for i in range(n):
            try:
                names.append(str(action.get_action_name(i) or f"action_{i}"))
            except Exception:
                names.append(f"action_{i}")
        return names
    except Exception:
        return []


def _do_action(accessible: Any, name: str) -> bool:
    try:
        action = accessible.get_action_iface()
        if action is None:
            return False
        n = int(action.get_n_actions() or 0)
        for i in range(n):
            try:
                if str(action.get_action_name(i) or "") == name:
                    return bool(action.do_action(i))
            except Exception:
                continue
        # case-insensitive fallback
        for i in range(n):
            try:
                if str(action.get_action_name(i) or "").lower() == name.lower():
                    return bool(action.do_action(i))
            except Exception:
                continue
        return False
    except Exception:
        return False


def _try_set_text(accessible: Any, text: str) -> bool:
    try:
        # EditableText interface
        et = accessible.get_editable_text_iface()
        if et is not None:
            # set_text_contents if available
            if hasattr(et, "set_text_contents"):
                return bool(et.set_text_contents(text))
    except Exception:
        pass
    try:
        # Some bindings expose set_text on Accessible
        if hasattr(accessible, "set_text_contents"):
            return bool(accessible.set_text_contents(text))
    except Exception:
        pass
    return False


def _bounds(accessible: Any) -> Bounds | None:
    try:
        component = accessible.get_component_iface()
        if component is None:
            return None
        # DESKTOP_COORDS = 0 typically
        try:
            from gi.repository import Atspi

            coords = Atspi.CoordType.DESKTOP
        except Exception:
            coords = 0
        rect = component.get_extents(coords)
        if rect is None:
            return None
        w = float(getattr(rect, "width", 0) or 0)
        h = float(getattr(rect, "height", 0) or 0)
        if w <= 0 or h <= 0:
            return None
        return Bounds(
            x=float(getattr(rect, "x", 0) or 0),
            y=float(getattr(rect, "y", 0) or 0),
            width=w,
            height=h,
        )
    except Exception:
        return None


def _map_actions(role: str, action_names: list[str], states: list[str]) -> list[ActionKind]:
    caps: list[ActionKind] = []
    role_l = role.lower()
    names_l = {n.lower() for n in action_names}
    editable = any(s.lower() == "editable" for s in states) or role_l in _TEXT_ROLES

    if names_l & {"click", "press", "activate", "jump"} or role_l in _CLICK_ROLES:
        caps.append(ActionKind.CLICK)
    if "showmenu" in names_l or "menu" in names_l:
        if ActionKind.CLICK not in caps:
            caps.append(ActionKind.CLICK)
        caps.append(ActionKind.RIGHT_CLICK)

    if editable or role_l in _TEXT_ROLES:
        if ActionKind.CLICK not in caps:
            caps.append(ActionKind.CLICK)
        caps.append(ActionKind.TYPE_TEXT)
        if role_l in _VALUE_ROLES:
            caps.append(ActionKind.SET_VALUE)

    # List / tree items often open on double-click
    if role_l in {"list item", "tree item", "table cell"} and ActionKind.CLICK in caps:
        caps.append(ActionKind.DOUBLE_CLICK)

    # Dedupe preserve order
    seen: set[ActionKind] = set()
    out: list[ActionKind] = []
    for c in caps:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _stable_id(accessible: Any) -> str:
    parts = [
        _safe_role(accessible),
        _safe_name(accessible),
        str(_safe_value(accessible) or ""),
    ]
    try:
        path = accessible.get_path()
        if path:
            parts.append(str(path))
    except Exception:
        pass
    try:
        parts.append(str(accessible.get_index_in_parent()))
    except Exception:
        pass
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
    return f"atspi_{digest}"
