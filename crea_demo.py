#!/usr/bin/env python3
"""Crea/aggiorna dati demo su PostgreSQL.

Da v72 GiroFacile non usa più SQLite. Questo comando inizializza lo schema
PostgreSQL e verifica l'account demo usando DATABASE_URL nel file .env.
"""
from scripts.init_postgres_demo import *  # noqa: F401,F403
