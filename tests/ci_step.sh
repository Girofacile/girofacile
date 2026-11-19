#!/usr/bin/env bash
# Esegue un passaggio dei controlli su GitHub con un limite di tempo e, se fallisce,
# pubblica le ultime righe dell'uscita come avviso visibile nella pagina del controllo
# (leggibile anche senza accesso ai registri completi).
#
# Uso: bash tests/ci_step.sh <minuti> "<titolo>" python -X faulthandler tests/xxx.py [argomenti]
# Allo scadere il comando riceve SIGABRT: con -X faulthandler Python stampa dove era fermo.
set -u
minutes="$1"; title="$2"; shift 2
log="$(mktemp)"
set -o pipefail
timeout -s ABRT "${minutes}m" "$@" 2>&1 | tee "$log"
code=${PIPESTATUS[0]}
if [ "$code" -ne 0 ]; then
  reason="uscita $code"
  if [ "$code" -eq 124 ] || [ "$code" -eq 134 ]; then reason="fermato dopo $minutes minuti (bloccato o troppo lento)"; fi
  python3 tests/ci_annotate.py "$title — $reason" "$log"
fi
exit "$code"
