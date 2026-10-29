"""Read-only HTTP API over the data the ingest layer has already loaded.

The API answers one question: what do the sources this system has ingested say
about a clinician, and as of when. It makes no outbound request, writes nothing,
and reports only on sources that have produced evidence rows. Every lookup
response carries a ``sources`` block naming what was read, what was not, and the
date each snapshot was fetched.

Run it with::

    pip install -e ".[api]"
    API_KEYS=... API_DATABASE_URL=... \\
      uvicorn --factory clinician_standing.api.app:create_app

See the "Standing API" section of the README.
"""

from __future__ import annotations

__all__: list[str] = []
