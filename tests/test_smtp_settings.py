"""Email di invio: i valori salvati nel pannello Super Admin prevalgono su quelli del .env."""
from app.services import email, platform_settings


def test_panel_values_override_environment(monkeypatch):
    saved = {"smtp_host": "smtp.pannello.it", "smtp_port": "2525", "smtp_user": "invio@esempio.it", "smtp_password": "segreta"}
    monkeypatch.setattr(platform_settings, "get_platform_setting", lambda db, key, default="": saved.get(key, default))
    cfg = email.smtp_config()
    assert (cfg["host"], cfg["port"], cfg["user"], cfg["password"]) == ("smtp.pannello.it", 2525, "invio@esempio.it", "segreta")
    assert cfg["from"] == "invio@esempio.it"  # mittente vuoto: si usa la casella


def test_environment_is_the_fallback(monkeypatch):
    monkeypatch.setattr(platform_settings, "get_platform_setting", lambda db, key, default="": default)
    monkeypatch.setattr(email, "SMTP_HOST", "smtp.ionos.it")
    cfg = email.smtp_config()
    assert cfg["host"] == "smtp.ionos.it" and isinstance(cfg["port"], int)


def test_send_without_credentials_does_not_connect(monkeypatch):
    monkeypatch.setattr(platform_settings, "get_platform_setting", lambda db, key, default="": default)
    monkeypatch.setattr(email, "SMTP_USER", "")
    monkeypatch.setattr(email, "SMTP_PASSWORD", "")
    monkeypatch.setattr(email.smtplib, "SMTP", lambda *a, **k: (_ for _ in ()).throw(AssertionError("nessuna connessione")))
    assert email._send("a@b.it", "prova", "<p>x</p>") is False
