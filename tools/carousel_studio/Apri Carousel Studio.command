#!/bin/bash
# Finder apre questo file in Terminale, fuori dal ciclo di vita della chat.
cd -- "$(dirname -- "$0")" || exit 1
python3 launcher.py
result=$?
if [ "$result" -ne 0 ]; then
  printf '\nAvvio non riuscito. Leggi il messaggio sopra. Premi Invio per chiudere.'
  read -r
fi
exit "$result"
