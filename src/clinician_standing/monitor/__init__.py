"""Clinician Standing Monitor (T620): re-read standing for every rostered NPI after each
source run, diff it against the last snapshot and write one alert per change.

The monitor calls :func:`clinician_standing.api.service.check`, so a monitor result and an API
lookup cannot disagree. Provider data only; the roster holds NPI, name, state and credential.
"""

from .diff import Alert, diff_snapshots
from .run import run_monitor
from .snapshot import Snapshot, take_snapshot

__all__ = ["Alert", "Snapshot", "diff_snapshots", "run_monitor", "take_snapshot"]
