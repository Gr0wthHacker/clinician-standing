"""Alert delivery behind an interface. No email vendor is chosen yet, so the vendor is set by
``STANDING_MONITOR_NOTIFIER`` (``none`` by default, or ``outbox`` to write .eml-style files to
``STANDING_MONITOR_OUTBOX`` for a person to send). A real vendor adds one class here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

__all__ = ["Message", "Notifier", "NullNotifier", "OutboxNotifier", "notifier_from_env"]


@dataclass(frozen=True)
class Message:
    to: str
    subject: str
    body: str
    ref: str


class Notifier(Protocol):
    def send(self, message: Message) -> bool: ...


class NullNotifier:
    """Sends nothing and reports failure, so alerts stay pending until a vendor is set."""

    def send(self, message: Message) -> bool:
        return False


class OutboxNotifier:
    def __init__(self, directory: str | Path) -> None:
        self.dir = Path(directory)

    def send(self, message: Message) -> bool:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{message.ref}.txt").write_text(
            f"To: {message.to}\nSubject: {message.subject}\n\n{message.body}\n", encoding="utf-8"
        )
        return True


def notifier_from_env(env: dict[str, str] | None = None) -> Notifier:
    env = dict(os.environ) if env is None else env
    kind = env.get("STANDING_MONITOR_NOTIFIER", "none").strip().lower()
    if kind == "outbox":
        return OutboxNotifier(env.get("STANDING_MONITOR_OUTBOX", "monitor-outbox"))
    if kind in ("", "none"):
        return NullNotifier()
    raise ValueError(f"unknown STANDING_MONITOR_NOTIFIER: {kind}")
