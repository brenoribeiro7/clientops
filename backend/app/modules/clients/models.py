from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (
        CheckConstraint("name = btrim(name) AND name <> ''", name="ck_clients_name"),
        CheckConstraint(
            "phone IS NULL OR phone = btrim(phone) AND phone <> ''", name="ck_clients_phone"
        ),
        CheckConstraint(
            "email IS NULL OR email = btrim(email) AND email <> ''", name="ck_clients_email"
        ),
        CheckConstraint(
            "address IS NULL OR address = btrim(address) AND address <> ''",
            name="ck_clients_address",
        ),
        CheckConstraint(
            "notes IS NULL OR notes = btrim(notes) AND notes <> ''", name="ck_clients_notes"
        ),
        CheckConstraint("status IN ('ACTIVE','ARCHIVED')", name="ck_clients_status"),
        CheckConstraint(
            "(status = 'ACTIVE' AND archived_at IS NULL) OR "
            "(status = 'ARCHIVED' AND archived_at IS NOT NULL)",
            name="ck_clients_archive_state",
        ),
        CheckConstraint("version > 0", name="ck_clients_version_positive"),
        Index("ix_clients_status_name_id", "status", "name", "id"),
        Index("ix_clients_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(5000), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    equipment: Mapped[list[Equipment]] = relationship(back_populates="client")


class Equipment(Base):
    __tablename__ = "equipment"
    __table_args__ = (
        UniqueConstraint("id", "client_id", name="uq_equipment_id_client_id"),
        CheckConstraint("name = btrim(name) AND name <> ''", name="ck_equipment_name"),
        CheckConstraint(
            "brand IS NULL OR brand = btrim(brand) AND brand <> ''", name="ck_equipment_brand"
        ),
        CheckConstraint(
            "model IS NULL OR model = btrim(model) AND model <> ''", name="ck_equipment_model"
        ),
        CheckConstraint(
            "serial_number IS NULL OR serial_number = btrim(serial_number) AND serial_number <> ''",
            name="ck_equipment_serial_number",
        ),
        CheckConstraint(
            "location_description IS NULL OR location_description = btrim(location_description) "
            "AND location_description <> ''",
            name="ck_equipment_location_description",
        ),
        CheckConstraint(
            "notes IS NULL OR notes = btrim(notes) AND notes <> ''", name="ck_equipment_notes"
        ),
        CheckConstraint("status IN ('ACTIVE','ARCHIVED')", name="ck_equipment_status"),
        CheckConstraint(
            "(status = 'ACTIVE' AND archived_at IS NULL) OR "
            "(status = 'ARCHIVED' AND archived_at IS NOT NULL)",
            name="ck_equipment_archive_state",
        ),
        CheckConstraint("version > 0", name="ck_equipment_version_positive"),
        Index("ix_equipment_client_status_name_id", "client_id", "status", "name", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, nullable=False)
    client_id: Mapped[UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location_description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(5000), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    client: Mapped[Client] = relationship(back_populates="equipment")
