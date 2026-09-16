from datetime import datetime
from sqlalchemy import Boolean, Float, Integer, String, Text, DateTime, Date, Time, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(200), unique=True, index=True, nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    company_logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    company_phone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    company_vat: Mapped[str | None] = mapped_column(String(80), nullable=True)
    company_fiscal_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    company_pec: Mapped[str | None] = mapped_column(String(200), nullable=True)
    company_sdi: Mapped[str | None] = mapped_column(String(20), nullable=True)
    company_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    company_city: Mapped[str | None] = mapped_column(String(150), nullable=True)
    company_zip: Mapped[str | None] = mapped_column(String(20), nullable=True)
    company_country: Mapped[str | None] = mapped_column(String(80), default="Italia")
    company_legal_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    company_billing_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    company_sector: Mapped[str | None] = mapped_column(String(120), nullable=True)
    company_activity_type: Mapped[str | None] = mapped_column(String(180), nullable=True)
    company_size: Mapped[str | None] = mapped_column(String(80), nullable=True)
    daily_deliveries: Mapped[str | None] = mapped_column(String(80), nullable=True)
    has_time_windows: Mapped[bool] = mapped_column(Boolean, default=True)
    needs_signature: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_photo_proof: Mapped[bool] = mapped_column(Boolean, default=False)
    has_refrigerated_goods: Mapped[bool] = mapped_column(Boolean, default=False)
    has_ztl: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_tail_lift: Mapped[bool] = mapped_column(Boolean, default=False)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    onboarding_dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    password_hash: Mapped[str] = mapped_column(String(300), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # --- Abbonamento / Piano ---
    plan: Mapped[str] = mapped_column(String(30), default="starter")
    # Stato: trial | active | expired | cancelled
    plan_status: Mapped[str] = mapped_column(String(30), default="trial")
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    plan_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # --- Stripe ---
    stripe_customer_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # --- Impostazioni operative aziendali ---
    delivery_signature_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class BillingInvoice(Base):
    __tablename__ = "billing_invoices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    invoice_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    period_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    plan_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    subtotal: Mapped[float] = mapped_column(Float, default=0)
    vat_amount: Mapped[float] = mapped_column(Float, default=0)
    total: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(10), default="EUR")
    status: Mapped[str] = mapped_column(String(30), default="paid", index=True)
    pdf_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BillingPayment(Base):
    __tablename__ = "billing_payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("billing_invoices.id", ondelete="SET NULL"), index=True, nullable=True)
    amount: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(10), default="EUR")
    payment_method: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payment_status: Mapped[str] = mapped_column(String(30), default="paid", index=True)
    transaction_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SaaSPlatformSetting(Base):
    """Impostazioni globali della piattaforma GiroFacile.

    Sono usate solo dal Super Admin: nome piattaforma, email supporto,
    registrazioni aperte/chiuse, manutenzione e preferenze di notifica.
    """
    __tablename__ = "saas_platform_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SuperAdminProfile(Base):
    """Profilo visuale/preferenze del proprietario SaaS.

    Le credenziali di accesso restano gestite tramite .env per sicurezza;
    qui salviamo dati di interfaccia e preferenze operative.
    """
    __tablename__ = "superadmin_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    avatar_initials: Mapped[str | None] = mapped_column(String(8), nullable=True)
    notify_errors: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_tickets: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_new_companies: Mapped[bool] = mapped_column(Boolean, default=True)
    last_access_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SuperAdminActivityLog(Base):
    """Registro attività del pannello Super Admin."""
    __tablename__ = "superadmin_activity_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    actor_username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    action: Mapped[str] = mapped_column(String(140), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(30), default="info", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class SuperAdminCollaborator(Base):
    """Collaboratori del pannello Super Admin SaaS.

    Sono profili separati dall'account proprietario e possono accedere solo
    alle funzioni abilitate dal Super Admin tramite permessi granulari.
    """
    __tablename__ = "superadmin_collaborators"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    full_name: Mapped[str] = mapped_column(String(180), nullable=False)
    email: Mapped[str] = mapped_column(String(220), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    role_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(300), nullable=False)
    permissions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    invitation_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    invited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_access_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ApiUsageLog(Base):
    """Registro interno consumi API esterne collegati alla piattaforma.

    Prima versione dedicata a Google Maps Platform: geocoding, verifica
    indirizzi, Routes API e futuri servizi. Serve al Super Admin per vedere
    quante chiamate vengono generate, da quale azienda e con quale esito.
    """
    __tablename__ = "api_usage_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    provider: Mapped[str] = mapped_column(String(80), default="google", index=True)
    service: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    action: Mapped[str | None] = mapped_column(String(180), nullable=True)
    endpoint: Mapped[str | None] = mapped_column(String(240), nullable=True)
    request_count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(30), default="success", index=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_eur: Mapped[float] = mapped_column(Float, default=0)
    meta_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class TransferBookingPortalSetting(Base):
    __tablename__ = "transfer_booking_portal_settings"
    __table_args__ = (UniqueConstraint("user_id", name="uq_transfer_portal_user"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    public_slug: Mapped[str] = mapped_column(String(180), unique=True, index=True, nullable=False)
    logo_data_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    theme: Mapped[str] = mapped_column(String(40), default="modern")
    primary_color: Mapped[str] = mapped_column(String(20), default="#0f766e")
    secondary_color: Mapped[str] = mapped_column(String(20), default="#ecfdf5")
    button_color: Mapped[str] = mapped_column(String(20), default="#0f766e")
    text_color: Mapped[str] = mapped_column(String(20), default="#102a2a")
    background_color: Mapped[str] = mapped_column(String(20), default="#f4fbfa")
    hero_image_data_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(String(220), default="Prenota il tuo transfer")
    subtitle: Mapped[str] = mapped_column(String(400), default="Inserisci i dati della corsa e riceverai rapidamente la conferma.")
    intro_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmation_message: Mapped[str] = mapped_column(Text, default="Richiesta inviata correttamente.")
    closed_message: Mapped[str] = mapped_column(Text, default="Le prenotazioni online sono momentaneamente sospese.")
    footer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    whatsapp: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    website: Mapped[str | None] = mapped_column(String(300), nullable=True)
    fields_json: Mapped[str] = mapped_column(Text, default="{}")
    services_json: Mapped[str] = mapped_column(Text, default="[]")
    portal_status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    accept_bookings: Mapped[bool] = mapped_column(Boolean, default=True)
    min_advance_minutes: Mapped[int] = mapped_column(Integer, default=30)
    show_girofacile_brand: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TransferBookingRequest(Base):
    __tablename__ = "transfer_booking_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    portal_id: Mapped[int] = mapped_column(ForeignKey("transfer_booking_portal_settings.id", ondelete="CASCADE"), index=True, nullable=False)
    customer_name: Mapped[str] = mapped_column(String(180), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    pickup_address: Mapped[str] = mapped_column(String(500), nullable=False)
    destination_address: Mapped[str] = mapped_column(String(500), nullable=False)
    pickup_date: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    pickup_time: Mapped[str] = mapped_column(String(10), nullable=False)
    passengers: Mapped[int] = mapped_column(Integer, default=1)
    luggage: Mapped[str | None] = mapped_column(String(120), nullable=True)
    service_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    flight_train: Mapped[str | None] = mapped_column(String(100), nullable=True)
    child_seat: Mapped[bool] = mapped_column(Boolean, default=False)
    pets: Mapped[bool] = mapped_column(Boolean, default=False)
    round_trip: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="new", index=True)
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id", ondelete="SET NULL"), index=True, nullable=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id", ondelete="SET NULL"), index=True, nullable=True)
    assignment_status: Mapped[str] = mapped_column(String(30), default="unassigned", index=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    booking_source: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class TransferBookingEvent(Base):
    __tablename__ = "transfer_booking_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("transfer_booking_requests.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class TransferOperationalSetting(Base):
    __tablename__ = "transfer_operational_settings"
    __table_args__ = (UniqueConstraint("user_id", name="uq_transfer_operational_user"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    dispatch_mode: Mapped[str] = mapped_column(String(30), default="manual")
    auto_strategy: Mapped[str] = mapped_column(String(40), default="best_fit")
    driver_response_seconds: Mapped[int] = mapped_column(Integer, default=60)
    notify_email: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_internal: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_driver_reject: Mapped[bool] = mapped_column(Boolean, default=True)
    min_buffer_minutes: Mapped[int] = mapped_column(Integer, default=15)
    airport_buffer_minutes: Mapped[int] = mapped_column(Integer, default=30)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)
    # Collegamento opzionale con un errore tecnico registrato nel Super Admin.
    # Quando il ticket viene chiuso, anche l'errore collegato viene marcato come risolto.
    system_error_id: Mapped[int | None] = mapped_column(ForeignKey("system_error_logs.id", ondelete="SET NULL"), index=True, nullable=True)
    tipo: Mapped[str] = mapped_column(String(80), default="recupero_password")
    email: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    oggetto: Mapped[str | None] = mapped_column(String(250), nullable=True)
    messaggio: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="aperto")
    notify_on_resolution: Mapped[bool] = mapped_column(Boolean, default=True)
    resolved_email_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Deposit(Base):
    __tablename__ = "deposits"
    __table_args__ = (Index("ix_deposits_company", "user_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    indirizzo: Mapped[str] = mapped_column(String(500), nullable=False)
    predefinito: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (Index("ix_agents_company", "user_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    codice_agente: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    cognome: Mapped[str | None] = mapped_column(String(150), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    zona: Mapped[str | None] = mapped_column(String(200), nullable=True)
    attivo: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (Index("ix_customers_company", "user_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), index=True, nullable=True)
    codice_cliente: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    nome: Mapped[str] = mapped_column(String(250), index=True, nullable=False)
    indirizzo: Mapped[str] = mapped_column(String(500), nullable=False)
    comune: Mapped[str | None] = mapped_column(String(150), nullable=True)
    provincia: Mapped[str | None] = mapped_column(String(50), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(100), nullable=True)
    referente: Mapped[str | None] = mapped_column(String(150), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    scarico_mattina_da: Mapped[object | None] = mapped_column(Time, nullable=True)
    scarico_mattina_a: Mapped[object | None] = mapped_column(Time, nullable=True)
    scarico_pomeriggio_da: Mapped[object | None] = mapped_column(Time, nullable=True)
    scarico_pomeriggio_a: Mapped[object | None] = mapped_column(Time, nullable=True)
    tempo_scarico_min: Mapped[int] = mapped_column(Integer, default=10)
    tempo_scarico_rilevazioni: Mapped[int] = mapped_column(Integer, default=0)
    ztl: Mapped[bool] = mapped_column(Boolean, default=False)
    sponda: Mapped[bool] = mapped_column(Boolean, default=False)
    transpallet: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    indirizzo_geocodificato: Mapped[str | None] = mapped_column(String(500), nullable=True)
    stato_geocodifica: Mapped[str] = mapped_column(String(30), default="da_verificare")
    affidabilita_geocodifica: Mapped[float | None] = mapped_column(Float, nullable=True)
    fonte_geocodifica: Mapped[str | None] = mapped_column(String(50), nullable=True)
    google_place_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    geocodificato_il: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    agent = relationship("Agent")


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (Index("ix_vehicles_company", "user_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    targa: Mapped[str | None] = mapped_column(String(50), nullable=True)
    consumo_l_100km: Mapped[float] = mapped_column(Float, default=8.5)
    capacita_kg: Mapped[float] = mapped_column(Float, default=1000)
    capacita_colli: Mapped[int] = mapped_column(Integer, default=100)
    ha_sponda: Mapped[bool] = mapped_column(Boolean, default=False)
    accesso_ztl: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)


class Driver(Base):
    __tablename__ = "drivers"
    __table_args__ = (Index("ix_drivers_company", "user_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    cognome: Mapped[str | None] = mapped_column(String(150), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(80), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    patente: Mapped[str | None] = mapped_column(String(80), nullable=True)
    scadenza_patente: Mapped[object | None] = mapped_column(Date, nullable=True)
    cqc: Mapped[bool] = mapped_column(Boolean, default=False)
    scadenza_cqc: Mapped[object | None] = mapped_column(Date, nullable=True)
    adr: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_admin_driver: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RoutePlan(Base):
    __tablename__ = "route_plans"
    __table_args__ = (Index("ix_route_plans_company", "user_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    nome: Mapped[str] = mapped_column(String(250), nullable=False)
    data_giro: Mapped[object] = mapped_column(Date, nullable=False)
    orario_partenza: Mapped[object] = mapped_column(Time, nullable=False)
    orario_rientro_stimato: Mapped[object | None] = mapped_column(Time, nullable=True)
    deposit_id: Mapped[int | None] = mapped_column(ForeignKey("deposits.id", ondelete="SET NULL"), nullable=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True)
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id", ondelete="SET NULL"), nullable=True)
    rientro_deposito: Mapped[bool] = mapped_column(Boolean, default=True)
    prezzo_carburante_litro: Mapped[float] = mapped_column(Float, default=1.75)
    totale_km: Mapped[float] = mapped_column(Float, default=0)
    totale_minuti: Mapped[float] = mapped_column(Float, default=0)
    litri_stimati: Mapped[float] = mapped_column(Float, default=0)
    costo_carburante: Mapped[float] = mapped_column(Float, default=0)
    costo_totale: Mapped[float] = mapped_column(Float, default=0)
    google_maps_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="programmato")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    deposit = relationship("Deposit")
    vehicle = relationship("Vehicle")
    driver = relationship("Driver")
    deliveries = relationship("Delivery", cascade="all, delete-orphan", passive_deletes=True)


class Delivery(Base):
    __tablename__ = "deliveries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    route_plan_id: Mapped[int] = mapped_column(ForeignKey("route_plans.id", ondelete="CASCADE"), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    cliente_nome: Mapped[str] = mapped_column(String(250), nullable=False)
    indirizzo: Mapped[str] = mapped_column(String(500), nullable=False)
    peso_kg: Mapped[float] = mapped_column(Float, default=0)
    colli: Mapped[int] = mapped_column(Integer, default=0)
    scarico_mattina_da: Mapped[object | None] = mapped_column(Time, nullable=True)
    scarico_mattina_a: Mapped[object | None] = mapped_column(Time, nullable=True)
    scarico_pomeriggio_da: Mapped[object | None] = mapped_column(Time, nullable=True)
    scarico_pomeriggio_a: Mapped[object | None] = mapped_column(Time, nullable=True)
    tempo_scarico_min: Mapped[int] = mapped_column(Integer, default=10)
    ztl: Mapped[bool] = mapped_column(Boolean, default=False)
    sponda: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    ordine: Mapped[int] = mapped_column(Integer, default=0)
    km_tappa: Mapped[float] = mapped_column(Float, default=0)
    minuti_tappa: Mapped[float] = mapped_column(Float, default=0)
    arrivo_stimato: Mapped[object | None] = mapped_column(Time, nullable=True)
    partenza_stimata: Mapped[object | None] = mapped_column(Time, nullable=True)
    attesa_min: Mapped[float] = mapped_column(Float, default=0)
    warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer = relationship("Customer")


class DeliveryStatus(Base):
    """Stato di ogni singola consegna durante l'esecuzione del giro."""
    __tablename__ = "delivery_statuses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("deliveries.id", ondelete="CASCADE"), nullable=False, index=True)
    route_plan_id: Mapped[int] = mapped_column(ForeignKey("route_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    # Stati: in_attesa | completata | mancata
    status: Mapped[str] = mapped_column(String(30), default="in_attesa")
    # Motivo mancata consegna: assente | chiuso | rifiutato | altro
    motivo_mancata: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tempo_scarico_effettivo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note_operatore: Mapped[str | None] = mapped_column(String(500), nullable=True)
    completata_il: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Firma cliente alla consegna
    signature_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    signed_by_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    signature_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class RouteToken(Base):
    """Token sicuro per accesso operatore al giro."""
    __tablename__ = "route_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    route_plan_id: Mapped[int] = mapped_column(ForeignKey("route_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DriverAccount(Base):
    """Account di accesso per l'autista al portale driver."""
    __tablename__ = "driver_accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id", ondelete="CASCADE"), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DriverSetupToken(Base):
    """Token per il setup iniziale della password dell'autista."""
    __tablename__ = "driver_setup_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AgentAccount(Base):
    """Account di accesso per l'agente al portale agenti."""
    __tablename__ = "agent_accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AgentSetupToken(Base):
    """Token per il setup iniziale della password dell'agente."""
    __tablename__ = "agent_setup_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PasswordResetToken(Base):
    """Token monouso per recupero password di account azienda/autisti.

    account_type: user | driver
    account_id: id della tabella corrispondente
    """
    __tablename__ = "password_reset_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    account_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    account_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)



class DistanceCache(Base):
    """Cache aziendale delle distanze/tempi tra due punti del giro.

    Ogni riga rappresenta una tratta A->B già calcolata con Google Routes.
    La cache è separata per azienda tramite user_id e scade automaticamente
    dopo un periodo configurabile, di default 15 giorni.
    """
    __tablename__ = "distance_cache"
    __table_args__ = (
        UniqueConstraint("user_id", "origin_key", "dest_key", name="uq_distance_cache_company_pair"),
        Index("ix_distance_cache_company_pair", "user_id", "origin_key", "dest_key"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    origin_key: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    dest_key: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    km: Mapped[float] = mapped_column(Float, nullable=False)
    min: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class Notification(Base):
    """Notifiche interne per la Dashboard amministratore."""
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    entity_key: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action_tab: Mapped[str | None] = mapped_column(String(80), nullable=True)
    action_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ActivityEvent(Base):
    """Registro attività aziendale.

    Salva gli eventi operativi importanti per audit interno:
    creazioni, modifiche, import, giri, consegne, chat e attività agenti/autisti.
    """
    __tablename__ = "activity_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    entity_key: Mapped[str] = mapped_column(String(220), unique=True, index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(70), index=True, nullable=False)
    actor_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(70), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action_tab: Mapped[str | None] = mapped_column(String(80), nullable=True)
    severity: Mapped[str] = mapped_column(String(30), default="info", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class ChatMessage(Base):
    """Messaggi chat tra autista e responsabile.

    route_plan_id viene mantenuto per la chat legata a un giro.
    Per la chat libera autista/amministratore usiamo route_plan_id=0
    e driver_id valorizzato, così non obblighiamo l'autista a scegliere un giro.
    """
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    route_plan_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id", ondelete="SET NULL"), nullable=True, index=True)
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "admin" | "driver"
    sender_name: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SystemErrorLog(Base):
    """Errori tecnici da mostrare al Super Admin.

    Non registra errori ordinari dell'utente come password errata, 401/403/404
    o validazioni normali: serve per bug reali, eccezioni server e problemi API.
    """
    __tablename__ = "system_error_logs"
    __table_args__ = (
        Index("ix_system_error_status_created", "status", "created_at"),
        Index("ix_system_error_company_created", "user_id", "created_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    company_sector: Mapped[str | None] = mapped_column(String(120), nullable=True)
    user_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    method: Mapped[str | None] = mapped_column(String(12), nullable=True)
    path: Mapped[str | None] = mapped_column(String(600), nullable=True)
    action: Mapped[str | None] = mapped_column(String(160), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(180), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    technical_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    browser: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(80), nullable=True)
    severity: Mapped[str] = mapped_column(String(30), default="high", index=True)
    status: Mapped[str] = mapped_column(String(30), default="new", index=True)
    email_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
