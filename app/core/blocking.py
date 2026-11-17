"""Lavoro sincrono col database lanciato da gestori asincroni.

Un gestore `async def` che usa il database direttamente blocca il ciclo che serve
tutte le altre richieste: se aspetta una riga bloccata, rallenta anche pagine che
non c'entrano. Qui il lavoro gira in un thread a parte e l'attesa dei blocchi è limitata.
"""
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from starlette.concurrency import run_in_threadpool

LOCK_WAIT_SECONDS = 5
LOCK_TIMEOUT_PGCODE = '55P03'


def limit_lock_wait(db, seconds=LOCK_WAIT_SECONDS):
    """Su PostgreSQL l'attesa di una riga bloccata finisce dopo pochi secondi (vale per la transazione)."""
    if db.get_bind().dialect.name == 'postgresql':
        db.execute(text(f"SET LOCAL lock_timeout = '{int(seconds)}s'"))


async def run_db(db, fn, *args, **kwargs):
    def call():
        try:
            limit_lock_wait(db)
            return fn(*args, **kwargs)
        except OperationalError as exc:
            db.rollback()
            if getattr(getattr(exc, 'orig', None), 'pgcode', None) == LOCK_TIMEOUT_PGCODE:
                raise HTTPException(503, 'Servizio momentaneamente occupato: riprova tra poco.',
                                    headers={'Retry-After': '10'})
            raise
    return await run_in_threadpool(call)
