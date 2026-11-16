"""Platform sales records, intentionally separate from tenant customers."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, Boolean, Index, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base
from .core.clock import utc_now


class CRMRecord:
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)


class CRMCompany(CRMRecord, Base):
    __tablename__ = 'crm_companies'
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(220), default='')
    phone: Mapped[str] = mapped_column(String(80), default='')
    vat: Mapped[str | None] = mapped_column(String(80), nullable=True)
    country: Mapped[str] = mapped_column(String(2), default='IT')
    sector: Mapped[str] = mapped_column(String(120), default='')
    city: Mapped[str] = mapped_column(String(150), default='')
    source: Mapped[str] = mapped_column(String(120), default='')
    interest: Mapped[str] = mapped_column(String(30), default='unknown', nullable=False)
    notes: Mapped[str] = mapped_column(Text, default='')
    owner_id: Mapped[int | None] = mapped_column(ForeignKey('superadmin_collaborators.id', ondelete='SET NULL'), index=True, nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    __table_args__ = (Index('uq_crm_company_vat', 'country', 'vat', unique=True),
                     CheckConstraint("interest IN ('unknown','interested','later','not_interested')", name='ck_crm_interest'))


class CRMContact(CRMRecord, Base):
    __tablename__ = 'crm_contacts'
    company_id: Mapped[int] = mapped_column(ForeignKey('crm_companies.id', ondelete='RESTRICT'), index=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(120), default='')
    email: Mapped[str] = mapped_column(String(220), default='')
    phone: Mapped[str] = mapped_column(String(80), default='')
    do_not_contact: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default='')


class CRMOpportunity(CRMRecord, Base):
    __tablename__ = 'crm_opportunities'
    company_id: Mapped[int] = mapped_column(ForeignKey('crm_companies.id', ondelete='RESTRICT'), index=True)
    title: Mapped[str] = mapped_column(String(200))
    stage: Mapped[str] = mapped_column(String(30), default='new', index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    probability: Mapped[int] = mapped_column(Integer, default=0)
    expected_close: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    lost_reason: Mapped[str] = mapped_column(String(500), default='')
    notes: Mapped[str] = mapped_column(Text, default='')
    __table_args__ = (CheckConstraint('amount >= 0 AND probability BETWEEN 0 AND 100', name='ck_crm_opportunity_value'),
                     CheckConstraint("stage IN ('new','contacted','qualified','demo','proposal','negotiation','won','lost')", name='ck_crm_stage'))


class CRMFollowup(CRMRecord, Base):
    __tablename__ = 'crm_followups'
    company_id: Mapped[int] = mapped_column(ForeignKey('crm_companies.id', ondelete='RESTRICT'), index=True)
    title: Mapped[str] = mapped_column(String(200))
    due_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(20), default='open', index=True)
    priority: Mapped[str] = mapped_column(String(20), default='normal')
    notes: Mapped[str] = mapped_column(Text, default='')
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (CheckConstraint("status IN ('open','completed','cancelled')", name='ck_crm_followup_status'),
                     CheckConstraint("priority IN ('normal','high')", name='ck_crm_followup_priority'))


class CRMActivity(CRMRecord, Base):
    __tablename__ = 'crm_activities'
    company_id: Mapped[int] = mapped_column(ForeignKey('crm_companies.id', ondelete='RESTRICT'), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    notes: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    actor: Mapped[str] = mapped_column(String(220))


class CRMAudit(Base):
    __tablename__ = 'crm_audit_events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey('crm_companies.id', ondelete='RESTRICT'), index=True)
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(120))
    actor: Mapped[str] = mapped_column(String(220))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


CRM_TABLES = [m.__table__ for m in (CRMCompany, CRMContact, CRMOpportunity, CRMFollowup, CRMActivity, CRMAudit)]
