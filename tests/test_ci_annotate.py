"""Avvisi dei controlli su GitHub: le ultime righe dell'errore diventano un avviso leggibile."""
from ci_annotate import annotation


def test_last_lines_become_one_github_error_annotation():
    log = "\n".join(f"riga {i}" for i in range(100)) + "\nAssertionError: 50% fallito"
    text = annotation("Flusso ordine giro autista — uscita 1", log)
    assert text.startswith("::error title=Flusso ordine giro autista — uscita 1::")
    body = text.split("::", 2)[2]
    assert "\n" not in body and "%0A" in body
    assert body.endswith("AssertionError: 50%25 fallito")
    assert "riga 40" not in body and "riga 41" in body


def test_title_cannot_break_the_command_format():
    assert annotation("a::b, c", "x").startswith("::error title=a: b; c::")
    assert annotation("vuoto", "").endswith("(nessuna uscita)")


def test_very_long_lines_do_not_hide_the_final_summary():
    log = "\n".join(["{" + "x" * 50000 + "}"] * 3 + ["RIEPILOGO regressioni 12"])
    body = annotation("t", log).split("::", 2)[2]
    assert len(body) < 4000 and body.endswith("RIEPILOGO regressioni 12")
