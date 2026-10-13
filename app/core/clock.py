"""Orologio UTC condiviso.

Il database salva istanti UTC senza fuso (colonne naive). ``utc_now`` ne
mantiene la semantica senza usare ``utcnow()`` di ``datetime``, deprecato da
Python 3.12 e destinato alla rimozione.
"""
from datetime import datetime, timezone


def utc_now() -> datetime:
    """Istante attuale in UTC, senza informazione di fuso (naive)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
