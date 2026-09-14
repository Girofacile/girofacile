"""
Servizio email — invio tramite SMTP Ionos.
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ..core.config import LOCAL_TIMEZONE, APP_BASE_URL

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.ionos.it")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "GiroFacile")


_EMAIL_FAILURE_LOGGING = False


def _log_email_failure(subject: str, to_email: str, reason: str, severity: str = "critical") -> None:
    """Registra nel Super Admin anche i problemi SMTP.

    Se l'invio email non funziona, non possiamo garantire una notifica esterna,
    ma l'errore deve comunque comparire in Errori sistema. Usiamo un guard
    per evitare loop nel caso in cui fallisca proprio la notifica di errore.
    """
    global _EMAIL_FAILURE_LOGGING
    if _EMAIL_FAILURE_LOGGING:
        return
    _EMAIL_FAILURE_LOGGING = True
    try:
        from datetime import datetime
        from ..database import SessionLocal
        from ..models import SystemErrorLog

        db = SessionLocal()
        try:
            row = SystemErrorLog(
                user_role="system",
                method="SMTP",
                path="email-service",
                action="Invio email",
                error_type="SMTPConfigurationError",
                error_message=(reason or "Errore invio email")[:3000],
                technical_details=(
                    f"Destinatario: {to_email or '—'}\n"
                    f"Oggetto: {subject or '—'}\n"
                    f"SMTP_HOST: {SMTP_HOST or '—'}\n"
                    f"SMTP_PORT: {SMTP_PORT or '—'}\n"
                    f"SMTP_USER presente: {'sì' if SMTP_USER else 'no'}\n"
                    f"SMTP_PASSWORD presente: {'sì' if SMTP_PASSWORD else 'no'}\n"
                    f"SMTP_FROM: {SMTP_FROM or '—'}"
                )[:12000],
                severity=severity,
                status="new",
                email_sent=False,
                created_at=datetime.utcnow(),
            )
            db.add(row)
            db.commit()
        finally:
            db.close()
    except Exception as monitor_exc:
        print(f"[EMAIL_MONITOR] Impossibile registrare errore SMTP: {monitor_exc}")
    finally:
        _EMAIL_FAILURE_LOGGING = False


def _send(to_email: str, subject: str, html_body: str) -> bool:
    """Invia una email HTML. Ritorna True se ok, False se errore."""
    if not SMTP_USER or not SMTP_PASSWORD:
        reason = "SMTP non configurato correttamente: SMTP_USER o SMTP_PASSWORD mancante"
        print(f"[EMAIL] {reason} — email a {to_email} non inviata")
        _log_email_failure(subject, to_email, reason, severity="critical")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM}>"
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [to_email], msg.as_string())
        print(f"[EMAIL] Inviata a {to_email}: {subject}")
        return True
    except Exception as e:
        reason = f"Errore invio email: {e}"
        print(f"[EMAIL] Errore invio a {to_email}: {e}")
        _log_email_failure(subject, to_email, reason, severity="critical")
        return False


def _base_template(content: str) -> str:
    return f"""
<!DOCTYPE html>
<html lang="it">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body{{margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;}}
  .wrap{{max-width:560px;margin:32px auto;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.08);}}
  .header{{background:#2563eb;padding:24px 32px;text-align:center;}}
  .header h1{{color:#fff;font-size:22px;font-weight:800;margin:0;}}
  .header p{{color:rgba(255,255,255,.8);font-size:13px;margin:4px 0 0;}}
  .body{{padding:28px 32px;}}
  .body p{{font-size:15px;color:#374151;line-height:1.6;margin-bottom:14px;}}
  .body strong{{color:#111827;}}
  .btn{{display:block;width:100%;padding:14px;background:#2563eb;color:#fff;text-align:center;text-decoration:none;border-radius:10px;font-size:16px;font-weight:700;margin:20px 0;}}
  .info-box{{background:#eff6ff;border-radius:10px;padding:16px;margin:16px 0;}}
  .info-row{{display:flex;gap:10px;font-size:14px;color:#374151;margin-bottom:6px;}}
  .info-row:last-child{{margin-bottom:0;}}
  .info-label{{color:#6b7280;width:120px;flex-shrink:0;}}
  .footer{{padding:16px 32px 24px;text-align:center;font-size:12px;color:#9ca3af;border-top:1px solid #f3f4f6;}}
  .warn{{background:#fef3c7;border-radius:8px;padding:12px 16px;font-size:13px;color:#92400e;margin:12px 0;}}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <h1>GiroFacile</h1>
    <p>Gestione consegne professionale</p>
  </div>
  <div class="body">{content}</div>
  <div class="footer">
    © GiroFacile · <a href="https://girofacile.it" style="color:#2563eb">girofacile.it</a><br>
    Questa email è stata inviata automaticamente, non rispondere a questo messaggio.
  </div>
</div>
</body>
</html>"""


# -----------------------------------------------------------------------
# Email assegnazione giro all'autista
# -----------------------------------------------------------------------

def send_route_assignment(
    to_email: str,
    driver_name: str,
    route_name: str,
    data_giro: str,
    orario_partenza: str,
    deposit_nome: str,
    n_consegne: int,
    km_totali: float,
    link_portale: str,
) -> bool:
    subject = f"🚚 Giro assegnato — {data_giro} ore {orario_partenza}"
    content = f"""
    <p>Ciao <strong>{driver_name}</strong>,</p>
    <p>Ti è stato assegnato un nuovo giro di consegne. Ecco il riepilogo:</p>
    <div class="info-box">
      <div class="info-row"><span class="info-label">Giro:</span><strong>{route_name}</strong></div>
      <div class="info-row"><span class="info-label">Data:</span><strong>{data_giro}</strong></div>
      <div class="info-row"><span class="info-label">Partenza:</span><strong>ore {orario_partenza} da {deposit_nome}</strong></div>
      <div class="info-row"><span class="info-label">Fermate:</span><strong>{n_consegne} consegne</strong></div>
      <div class="info-row"><span class="info-label">Km stimati:</span><strong>{km_totali:.1f} km</strong></div>
    </div>
    <p>Clicca il pulsante qui sotto per aprire il portale di consegna sul tuo telefono:</p>
    <a class="btn" href="{link_portale}">📱 Apri portale consegne</a>
    <div class="warn">⚠️ Il link è personale e valido per 3 giorni. Non condividerlo con altri.</div>
    <p>Per qualsiasi problema contatta il responsabile del giro.</p>
    """
    return _send(to_email, subject, _base_template(content))


# -----------------------------------------------------------------------
# Email promemoria 1 ora prima
# -----------------------------------------------------------------------

def send_route_reminder(
    to_email: str,
    driver_name: str,
    route_name: str,
    orario_partenza: str,
    deposit_nome: str,
    link_portale: str,
) -> bool:
    subject = f"⏰ Promemoria — giro tra 1 ora · {orario_partenza}"
    content = f"""
    <p>Ciao <strong>{driver_name}</strong>,</p>
    <p>Ti ricordiamo che tra circa <strong>1 ora</strong> inizia il tuo giro di consegne.</p>
    <div class="info-box">
      <div class="info-row"><span class="info-label">Giro:</span><strong>{route_name}</strong></div>
      <div class="info-row"><span class="info-label">Partenza:</span><strong>ore {orario_partenza} da {deposit_nome}</strong></div>
    </div>
    <a class="btn" href="{link_portale}">📱 Apri portale consegne</a>
    <p>Buon lavoro!</p>
    """
    return _send(to_email, subject, _base_template(content))


# -----------------------------------------------------------------------
# Email benvenuto registrazione
# -----------------------------------------------------------------------

def send_welcome(
    to_email: str,
    username: str,
    company_name: str,
    trial_days: int,
    app_url: str = "https://app.girofacile.it",
) -> bool:
    subject = "🎉 Benvenuto in GiroFacile — La tua prova gratuita è iniziata"
    content = f"""
    <p>Ciao <strong>{username}</strong>,</p>
    <p>Benvenuto in <strong>GiroFacile</strong>! Il tuo account per <strong>{company_name}</strong> è stato creato con successo.</p>
    <div class="info-box">
      <div class="info-row"><span class="info-label">Account:</span><strong>{username}</strong></div>
      <div class="info-row"><span class="info-label">Prova gratuita:</span><strong>{trial_days} giorni</strong></div>
    </div>
    <p>Hai <strong>{trial_days} giorni gratuiti</strong> per esplorare tutte le funzionalità senza impegno e senza carta di credito.</p>
    <a class="btn" href="{app_url}">🚀 Accedi al gestionale</a>
    <p>Se hai domande o hai bisogno di supporto, rispondi a questa email o scrivici a <a href="mailto:info@girofacile.it">info@girofacile.it</a>.</p>
    """
    return _send(to_email, subject, _base_template(content))


# -----------------------------------------------------------------------
# Email scadenza trial
# -----------------------------------------------------------------------

def send_trial_expiring(
    to_email: str,
    username: str,
    giorni_rimasti: int,
    upgrade_url: str = "https://app.girofacile.it",
) -> bool:
    subject = f"⏳ La tua prova gratuita scade tra {giorni_rimasti} giorni"
    content = f"""
    <p>Ciao <strong>{username}</strong>,</p>
    <p>La tua prova gratuita di GiroFacile scade tra <strong>{giorni_rimasti} giorni</strong>.</p>
    <p>Per continuare ad usare GiroFacile senza interruzioni, scegli il piano più adatto alla tua attività:</p>
    <div class="info-box">
      <div class="info-row"><span class="info-label">Starter</span><strong>€19/mese — 30 clienti, 5 giri/giorno</strong></div>
      <div class="info-row"><span class="info-label">Business</span><strong>€39/mese — 150 clienti, 30 giri/giorno</strong></div>
      <div class="info-row"><span class="info-label">Pro</span><strong>€79/mese — tutto illimitato</strong></div>
    </div>
    <a class="btn" href="{upgrade_url}">⬆️ Scegli il tuo piano</a>
    <p>Hai domande? Scrivici a <a href="mailto:info@girofacile.it">info@girofacile.it</a> — siamo felici di aiutarti.</p>
    """
    return _send(to_email, subject, _base_template(content))


def send_driver_invitation(
    to_email: str,
    driver_name: str,
    company_name: str,
    setup_url: str,
    admin_name: str | None = None,
    portal_url: str | None = None,
    is_reinvite: bool = False,
) -> bool:
    admin_label = admin_name or company_name or "L'amministratore"
    subject = f"🚛 {company_name} ti ha aggiunto come autista su GiroFacile"
    intro = "ti ha reinvitato ad accedere" if is_reinvite else "ti ha aggiunto come autista"
    content = f"""
    <p>Ciao <strong>{driver_name}</strong>,</p>
    <p>L'amministratore <strong>{admin_label}</strong> {intro} alla flotta di <strong>{company_name}</strong> su GiroFacile.</p>
    <p>Dal tuo portale potrai vedere soltanto i giri assegnati a te, consultare le consegne da effettuare e aggiornare lo stato delle fermate.</p>
    <p>Clicca il pulsante qui sotto per impostare la password e accedere al tuo portale autista:</p>
    <a class="btn" href="{setup_url}">🚛 Accedi al portale autista</a>
    <div class="info-box">
      <div class="info-row"><span class="info-label">Azienda:</span><strong>{company_name}</strong></div>
      <div class="info-row"><span class="info-label">Portale:</span><strong>I miei giri, consegne, note e chat col responsabile</strong></div>
      <div class="info-row"><span class="info-label">Link valido:</span><strong>7 giorni</strong></div>
    </div>
    <div class="warn">⚠️ Questo link è personale e serve per il primo accesso. Non condividerlo con altre persone.</div>
    <p>Dopo il primo accesso potrai entrare dal portale autista usando email e password.</p>
    {f'<p>Link portale: <a href="{portal_url}">{portal_url}</a></p>' if portal_url else ''}
    """
    return _send(to_email, subject, _base_template(content))


def send_driver_route_assigned(to_email, driver_name, company_name, route_name, data_giro, orario_partenza, n_consegne, km_totali, portal_url):
    subject = f"🚚 Nuovo giro assegnato — {data_giro}"
    content = f"""
    <p>Ciao <strong>{driver_name}</strong>,</p>
    <p><strong>{company_name}</strong> ti ha assegnato un nuovo giro di consegne.</p>
    <div class="info-box">
      <div class="info-row"><span class="info-label">Giro:</span><strong>{route_name}</strong></div>
      <div class="info-row"><span class="info-label">Data:</span><strong>{data_giro}</strong></div>
      <div class="info-row"><span class="info-label">Partenza:</span><strong>ore {orario_partenza}</strong></div>
      <div class="info-row"><span class="info-label">Fermate:</span><strong>{n_consegne} consegne · {km_totali:.1f} km</strong></div>
    </div>
    <a class="btn" href="{portal_url}">🚛 Visualizza nel portale autista</a>"""
    return _send(to_email, subject, _base_template(content))


def send_driver_route_reminder(to_email, driver_name, route_name, data_giro, orario_partenza, n_consegne, portal_url):
    subject = f"⏰ Promemoria giro — oggi ore {orario_partenza}"
    content = f"""
    <p>Ciao <strong>{driver_name}</strong>,</p>
    <p>Tra circa <strong>1 ora</strong> inizia il tuo giro di consegne.</p>
    <div class="info-box">
      <div class="info-row"><span class="info-label">Giro:</span><strong>{route_name}</strong></div>
      <div class="info-row"><span class="info-label">Partenza:</span><strong>ore {orario_partenza} — {n_consegne} fermate</strong></div>
    </div>
    <a class="btn" href="{portal_url}">🚛 Apri portale autista</a>
    <p>Buon lavoro!</p>"""
    return _send(to_email, subject, _base_template(content))


def send_password_reset(
    to_email: str,
    display_name: str,
    reset_url: str,
    account_label: str = "Account GiroFacile",
) -> bool:
    subject = "🔐 Reimposta la password del tuo account GiroFacile"
    safe_name = display_name or "utente"
    content = f"""
    <p>Ciao <strong>{safe_name}</strong>,</p>
    <p>Abbiamo ricevuto una richiesta di recupero password per il tuo <strong>{account_label}</strong>.</p>
    <p>Clicca sul pulsante qui sotto per impostare una nuova password:</p>
    <a class="btn" href="{reset_url}">Reimposta password</a>
    <div class="info-box">
      <div class="info-row"><span class="info-label">Validità:</span><strong>1 ora</strong></div>
      <div class="info-row"><span class="info-label">Sicurezza:</span><strong>link utilizzabile una sola volta</strong></div>
    </div>
    <div class="warn">Se non hai richiesto tu questa operazione, puoi ignorare questa email.</div>
    <p>Puoi sempre accedere dal dominio ufficiale: <a href="{APP_BASE_URL}">{APP_BASE_URL}</a></p>
    """
    return _send(to_email, subject, _base_template(content))


def send_agent_invitation(
    to_email: str,
    agent_name: str,
    company_name: str,
    setup_url: str,
    admin_name: str | None = None,
    portal_url: str | None = None,
    is_reinvite: bool = False,
) -> bool:
    admin_label = admin_name or company_name or "L'amministratore"
    subject = f"👤 {company_name} ti ha aggiunto come agente su GiroFacile"
    intro = "ti ha reinvitato ad accedere" if is_reinvite else "ti ha aggiunto come agente"
    content = f"""
    <p>Ciao <strong>{agent_name}</strong>,</p>
    <p>L'amministratore <strong>{admin_label}</strong> {intro} all'azienda <strong>{company_name}</strong> su GiroFacile.</p>
    <p>Dal tuo portale potrai creare e gestire i clienti della tua zona, inserire le specifiche di consegna e importare clienti da file CSV/Excel.</p>
    <p>Clicca il pulsante qui sotto per impostare la password e accedere al tuo portale agente:</p>
    <a class="btn" href="{setup_url}">👤 Accedi al portale agente</a>
    <div class="info-box">
      <div class="info-row"><span class="info-label">Azienda:</span><strong>{company_name}</strong></div>
      <div class="info-row"><span class="info-label">Portale:</span><strong>Clienti, import CSV/Excel, verifica indirizzi Google</strong></div>
      <div class="info-row"><span class="info-label">Link valido:</span><strong>7 giorni</strong></div>
    </div>
    <div class="warn">⚠️ Questo link è personale e serve per il primo accesso. Non condividerlo con altre persone.</div>
    <p>Dopo il primo accesso potrai entrare dal portale agente usando email e password.</p>
    {f'<p>Link portale: <a href="{portal_url}">{portal_url}</a></p>' if portal_url else ''}
    """
    return _send(to_email, subject, _base_template(content))


def send_system_error_alert(to_email: str, error_payload: dict) -> bool:
    """Invia al Super Admin una notifica email per errori tecnici importanti."""
    subject = f"🚨 Errore GiroFacile #{error_payload.get('id', 'nuovo')} — {error_payload.get('severity', 'high').upper()}"
    def esc(v):
        import html
        return html.escape(str(v or '—'))
    details = error_payload.get('technical_details') or ''
    if len(details) > 1800:
        details = details[:1800] + "\n... dettagli troncati"
    content = f"""
    <p>È stato rilevato un errore tecnico importante su <strong>GiroFacile</strong>.</p>
    <div class="info-box">
      <div class="info-row"><span class="info-label">Azienda:</span><strong>{esc(error_payload.get('company_name'))}</strong></div>
      <div class="info-row"><span class="info-label">Utente:</span><strong>{esc(error_payload.get('username'))}</strong></div>
      <div class="info-row"><span class="info-label">Settore:</span><strong>{esc(error_payload.get('company_sector'))}</strong></div>
      <div class="info-row"><span class="info-label">Azione:</span><strong>{esc(error_payload.get('action'))}</strong></div>
      <div class="info-row"><span class="info-label">Pagina/API:</span><strong>{esc(error_payload.get('method'))} {esc(error_payload.get('path'))}</strong></div>
      <div class="info-row"><span class="info-label">Gravità:</span><strong>{esc(error_payload.get('severity'))}</strong></div>
      <div class="info-row"><span class="info-label">Errore:</span><strong>{esc(error_payload.get('error_type'))}</strong></div>
    </div>
    <p><strong>Messaggio:</strong><br>{esc(error_payload.get('error_message'))}</p>
    <div class="warn">Questo avviso esclude errori ordinari come password errata, accesso non autorizzato o validazioni utente.</div>
    <p><strong>Dettagli tecnici:</strong></p>
    <pre style="white-space:pre-wrap;background:#111827;color:#e5e7eb;border-radius:10px;padding:12px;font-size:12px;line-height:1.45;">{esc(details)}</pre>
    """
    return _send(to_email, subject, _base_template(content))



def send_ticket_resolved(to_email: str, ticket_payload: dict) -> bool:
    """Avvisa l'utente quando un ticket viene chiuso, se richiesto."""
    subject = f"✅ Ticket GiroFacile #{ticket_payload.get('id', '')} risolto"
    def esc(v):
        import html
        return html.escape(str(v or '—'))
    content = f"""
    <p>Ciao,</p>
    <p>Il tuo ticket di assistenza su <strong>GiroFacile</strong> è stato segnato come <strong>risolto</strong>.</p>
    <div class="info-box">
      <div class="info-row"><span class="info-label">Ticket:</span><strong>#{esc(ticket_payload.get('id'))}</strong></div>
      <div class="info-row"><span class="info-label">Oggetto:</span><strong>{esc(ticket_payload.get('oggetto'))}</strong></div>
      <div class="info-row"><span class="info-label">Stato:</span><strong>Risolto</strong></div>
    </div>
    <p><strong>Nota assistenza:</strong><br>{esc(ticket_payload.get('admin_note') or 'Il problema è stato risolto dal supporto GiroFacile.')}</p>
    <p>Puoi tornare a usare il gestionale normalmente. Se il problema dovesse ripresentarsi, apri un nuovo ticket dal menu Supporto.</p>
    """
    return _send(to_email, subject, _base_template(content))


def send_superadmin_collaborator_invitation(
    to_email: str,
    collaborator_name: str,
    temporary_password: str,
    permissions_label: str,
    login_url: str | None = None,
) -> bool:
    """Invita un collaboratore al pannello Super Admin GiroFacile."""
    login_url = login_url or f"{APP_BASE_URL.rstrip('/')}/admin/login"
    subject = "👥 Sei stato aggiunto come collaboratore Super Admin GiroFacile"
    content = f"""
    <p>Ciao <strong>{collaborator_name}</strong>,</p>
    <p>Sei stato aggiunto come <strong>collaboratore del pannello Super Admin di GiroFacile</strong>.</p>
    <p>Potrai accedere soltanto alle funzioni abilitate dal proprietario della piattaforma.</p>
    <div class="info-box">
      <div class="info-row"><span class="info-label">Email:</span><strong>{to_email}</strong></div>
      <div class="info-row"><span class="info-label">Password temporanea:</span><strong>{temporary_password}</strong></div>
      <div class="info-row"><span class="info-label">Permessi:</span><strong>{permissions_label}</strong></div>
    </div>
    <a class="btn" href="{login_url}">Accedi al portale Super Admin</a>
    <div class="warn">Per sicurezza conserva queste credenziali con attenzione. Il Super Admin può disattivare o modificare i tuoi permessi in qualsiasi momento.</div>
    """
    return _send(to_email, subject, _base_template(content))
