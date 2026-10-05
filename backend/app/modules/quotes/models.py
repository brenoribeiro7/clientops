from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    Numeric,
    Sequence,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

quote_number_sequence = Sequence("quote_number_seq")


class Quote(Base):
    __tablename__ = "quotes"
    __table_args__ = (
        UniqueConstraint("number", name="uq_quotes_number"),
        UniqueConstraint("id", "client_id", name="uq_quotes_id_client_id"),
        CheckConstraint("number > 0", name="ck_quotes_number_positive"),
        CheckConstraint(
            "status IN ('DRAFT','SENT','APPROVED','CANCELLED')", name="ck_quotes_status"
        ),
        CheckConstraint("currency = 'BRL'", name="ck_quotes_currency"),
        CheckConstraint(
            "subtotal >= 0 AND subtotal = total AND total <= 999999999.99",
            name="ck_quotes_totals",
        ),
        CheckConstraint(
            "source_quote_id IS NULL OR source_quote_id <> id",
            name="ck_quotes_source_not_self",
        ),
        CheckConstraint(
            "(sent_at IS NULL AND commercial_snapshot IS NULL) OR "
            "(sent_at IS NOT NULL AND commercial_snapshot IS NOT NULL)",
            name="ck_quotes_sent_snapshot_pair",
        ),
        CheckConstraint(
            "commercial_snapshot IS NULL OR "
            "(jsonb_typeof(commercial_snapshot) = 'object' AND "
            "commercial_snapshot -> 'schema_version' = '1'::jsonb)",
            name="ck_quotes_snapshot_version",
        ),
        CheckConstraint(
            "approved_at IS NULL OR approved_at >= sent_at", name="ck_quotes_approved_order"
        ),
        CheckConstraint(
            "cancelled_at IS NULL OR cancelled_at >= created_at", name="ck_quotes_cancelled_order"
        ),
        CheckConstraint(
            "(cancellation_reason IS NULL) OR "
            "(cancellation_reason = btrim(cancellation_reason) AND cancellation_reason <> '')",
            name="ck_quotes_cancellation_reason_text",
        ),
        CheckConstraint(
            "(status = 'DRAFT' AND sent_at IS NULL AND approved_at IS NULL AND "
            "cancelled_at IS NULL AND cancellation_reason IS NULL AND "
            "commercial_snapshot IS NULL) OR "
            "(status = 'SENT' AND sent_at IS NOT NULL AND approved_at IS NULL AND "
            "cancelled_at IS NULL AND cancellation_reason IS NULL AND "
            "commercial_snapshot IS NOT NULL) OR "
            "(status = 'APPROVED' AND sent_at IS NOT NULL AND approved_at IS NOT NULL AND "
            "cancelled_at IS NULL AND cancellation_reason IS NULL AND "
            "commercial_snapshot IS NOT NULL) OR "
            "(status = 'CANCELLED' AND approved_at IS NULL AND cancelled_at IS NOT NULL AND "
            "cancellation_reason IS NOT NULL)",
            name="ck_quotes_state",
        ),
        CheckConstraint("version > 0", name="ck_quotes_version_positive"),
        CheckConstraint(
            "notes IS NULL OR notes = btrim(notes) AND notes <> ''", name="ck_quotes_notes"
        ),
        Index("ix_quotes_status_valid_until", "status", "valid_until"),
        Index("ix_quotes_status_sent_at", "status", "sent_at"),
        Index("ix_quotes_client_created_id", "client_id", "created_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, nullable=False)
    number: Mapped[int] = mapped_column(
        BigInteger,
        quote_number_sequence,
        server_default=quote_number_sequence.next_value(),
        nullable=False,
    )
    client_id: Mapped[UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False
    )
    source_quote_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("quotes.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(5000), nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    commercial_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    items: Mapped[list[QuoteItem]] = relationship(
        back_populates="quote", order_by="QuoteItem.position"
    )
    public_accesses: Mapped[list[QuotePublicAccess]] = relationship(back_populates="quote")


class QuoteItem(Base):
    __tablename__ = "quote_items"
    __table_args__ = (
        UniqueConstraint(
            "quote_id",
            "position",
            name="uq_quote_items_quote_position",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "description = btrim(description) AND description <> ''",
            name="ck_quote_items_description",
        ),
        CheckConstraint("position BETWEEN 1 AND 100", name="ck_quote_items_position"),
        CheckConstraint(
            "quantity >= 0.001 AND quantity <= 9999.999", name="ck_quote_items_quantity"
        ),
        CheckConstraint(
            "unit_price >= 0 AND unit_price <= 9999999.99", name="ck_quote_items_unit_price"
        ),
        CheckConstraint(
            "line_total >= 0 AND line_total <= 999999999.99",
            name="ck_quote_items_line_total",
        ),
        CheckConstraint("version > 0", name="ck_quote_items_version_positive"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, nullable=False)
    quote_id: Mapped[UUID] = mapped_column(
        ForeignKey("quotes.id", ondelete="RESTRICT"), nullable=False
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    quote: Mapped[Quote] = relationship(back_populates="items")


class QuotePublicAccess(Base):
    __tablename__ = "quote_public_access"
    __table_args__ = (
        CheckConstraint(
            "octet_length(bearer_hash) = 32", name="ck_quote_public_access_bearer_hash"
        ),
        CheckConstraint("expires_at > created_at", name="ck_quote_public_access_expiry_order"),
        CheckConstraint(
            "(revoked_at IS NULL AND revocation_reason IS NULL) OR "
            "(revoked_at IS NOT NULL AND revocation_reason IS NOT NULL)",
            name="ck_quote_public_access_revocation_pair",
        ),
        CheckConstraint(
            "revocation_reason IS NULL OR revocation_reason IN "
            "('ROTATED','ADMIN_REVOKED','QUOTE_CANCELLED')",
            name="ck_quote_public_access_revocation_reason",
        ),
        Index(
            "uq_quote_public_access_active_quote",
            "quote_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index("ix_quote_public_access_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, nullable=False)
    quote_id: Mapped[UUID] = mapped_column(
        ForeignKey("quotes.id", ondelete="RESTRICT"), nullable=False
    )
    bearer_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    quote: Mapped[Quote] = relationship(back_populates="public_accesses")
