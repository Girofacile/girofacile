"""Order archive: additive tables, no dependency on transient delivery IDs."""
from datetime import datetime, date
from sqlalchemy import (Integer, String, Text, DateTime, Date, ForeignKey, ForeignKeyConstraint,
                        UniqueConstraint, CheckConstraint, Index, JSON)
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


class OrderSource(Base):
    __tablename__ = 'order_sources'
    __table_args__ = (UniqueConstraint('user_id', 'id'), UniqueConstraint('user_id', 'key'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default='not_configured', nullable=False)
    configuration: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    credential_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Order(Base):
    __tablename__ = 'orders'
    __table_args__ = (
        UniqueConstraint('user_id', 'id'),
        UniqueConstraint('user_id', 'source_id', 'external_id', name='uq_order_external_source'),
        ForeignKeyConstraint(['user_id', 'source_id'], ['order_sources.user_id', 'order_sources.id']),
        CheckConstraint("status IN ('nuovo','da_verificare','pronto','assegnato','in_consegna','consegnato','non_consegnato','annullato')", name='ck_order_status'),
        Index('ix_orders_company_received', 'user_id', 'received_at', 'id'),
        Index('ix_orders_company_status_received', 'user_id', 'status', 'received_at', 'id'),
        Index('ix_orders_company_requested', 'user_id', 'requested_date', 'id'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    external_id: Mapped[str] = mapped_column(String(160), nullable=False)
    number: Mapped[str] = mapped_column(String(160), nullable=False)
    external_customer_id: Mapped[str | None] = mapped_column(String(160))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey('customers.id'))
    recipient_name: Mapped[str | None] = mapped_column(String(200))
    delivery_address: Mapped[str | None] = mapped_column(String(500))
    requested_date: Mapped[date | None] = mapped_column(Date)
    original_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    operational_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    acquisition_status: Mapped[str] = mapped_column(String(30), default='received', nullable=False)
    verification_status: Mapped[str] = mapped_column(String(30), default='pending', nullable=False)
    delivery_status: Mapped[str] = mapped_column(String(30), default='not_assigned', nullable=False)
    status: Mapped[str] = mapped_column(String(30), default='nuovo', nullable=False)
    address_verification: Mapped[dict | None] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class OrderItem(Base):
    __tablename__ = 'order_items'
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'), index=True, nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint('order_id', 'line_number'),)


class OrderEvent(Base):
    __tablename__ = 'order_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'), index=True, nullable=False)
    actor: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    changes: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class OrderImportRun(Base):
    __tablename__ = 'order_import_runs'
    __table_args__ = (ForeignKeyConstraint(['user_id', 'source_id'], ['order_sources.user_id', 'order_sources.id']),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True, nullable=False)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    report: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class CustomerSourceMapping(Base):
    __tablename__ = 'customer_source_mappings'
    __table_args__ = (
        ForeignKeyConstraint(['user_id', 'source_id'], ['order_sources.user_id', 'order_sources.id']),
        UniqueConstraint('user_id', 'source_id', 'external_customer_id'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    external_customer_id: Mapped[str] = mapped_column(String(160), nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id'), nullable=False)


class RouteOrderAssignment(Base):
    __tablename__ = 'route_order_assignments'
    __table_args__ = (
        ForeignKeyConstraint(['user_id', 'order_id'], ['orders.user_id', 'orders.id']),
        UniqueConstraint('order_id', name='uq_order_active_assignment'),
        Index('ix_order_assignment_route_stop', 'route_plan_id', 'stop_key'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    order_id: Mapped[int] = mapped_column(Integer, nullable=False)
    route_plan_id: Mapped[int] = mapped_column(ForeignKey('route_plans.id'), nullable=False)
    stop_key: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


ORDER_TABLES = [OrderSource.__table__, Order.__table__, OrderItem.__table__, OrderEvent.__table__,
                OrderImportRun.__table__, CustomerSourceMapping.__table__, RouteOrderAssignment.__table__]
