"""Optional Tesseract OCR perception — stub for v0.

macOS arc-cua uses Apple Vision OCR. A Linux OCR provider will land later
(Tesseract / similar). Keep the DesktopElement contract; do not block AT-SPI v0.
"""

from __future__ import annotations

from typing import Any

from ..models import DesktopElement


class LinuxOcrProvider:
    """Stub OCR provider. Raises until a real Tesseract path is wired."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._args = args
        self._kwargs = kwargs

    def capture_elements(self) -> tuple[DesktopElement, ...]:
        raise NotImplementedError(
            "LinuxOcrProvider is a v0 stub. Use LinuxAtspiBackend for semantic UI; "
            "Tesseract OCR will be added later without changing DesktopElement."
        )

    def observe_empty(self) -> tuple[DesktopElement, ...]:
        """Safe no-op for hybrid scaffolding — returns no OCR elements."""
        return ()
