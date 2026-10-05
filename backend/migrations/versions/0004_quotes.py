"""Add CL-04 quotes, public access, and quote timeline context."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_quotes"
down_revision: str | None = "0003_clients_equipment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE quote_number_seq START WITH 1 INCREMENT BY 1 NO CYCLE")
    op.create_table(
        "quotes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "number",
            sa.BigInteger(),
            server_default=sa.text("nextval('quote_number_seq')"),
            nullable=False,
        ),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("source_quote_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("notes", sa.String(5000), nullable=True),
        sa.Column("subtotal", sa.Numeric(14, 2), nullable=False),
        sa.Column("total", sa.Numeric(14, 2), nullable=False),
        sa.Column("commercial_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.String(1000), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_quotes"),
        sa.ForeignKeyConstraint(
            ["client_id"], ["clients.id"], ondelete="RESTRICT", name="fk_quotes_client"
        ),
        sa.ForeignKeyConstraint(
            ["source_quote_id"],
            ["quotes.id"],
            ondelete="RESTRICT",
            name="fk_quotes_source_quote",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="RESTRICT", name="fk_quotes_created_by"
        ),
        sa.UniqueConstraint("number", name="uq_quotes_number"),
        sa.UniqueConstraint("id", "client_id", name="uq_quotes_id_client_id"),
        sa.CheckConstraint("number > 0", name="ck_quotes_number_positive"),
        sa.CheckConstraint(
            "status IN ('DRAFT','SENT','APPROVED','CANCELLED')", name="ck_quotes_status"
        ),
        sa.CheckConstraint("currency = 'BRL'", name="ck_quotes_currency"),
        sa.CheckConstraint(
            "subtotal >= 0 AND subtotal = total AND total <= 999999999.99",
            name="ck_quotes_totals",
        ),
        sa.CheckConstraint(
            "source_quote_id IS NULL OR source_quote_id <> id",
            name="ck_quotes_source_not_self",
        ),
        sa.CheckConstraint(
            "(sent_at IS NULL AND commercial_snapshot IS NULL) OR "
            "(sent_at IS NOT NULL AND commercial_snapshot IS NOT NULL)",
            name="ck_quotes_sent_snapshot_pair",
        ),
        sa.CheckConstraint(
            "commercial_snapshot IS NULL OR "
            "(jsonb_typeof(commercial_snapshot) = 'object' AND "
            "commercial_snapshot -> 'schema_version' = '1'::jsonb)",
            name="ck_quotes_snapshot_version",
        ),
        sa.CheckConstraint(
            "approved_at IS NULL OR approved_at >= sent_at", name="ck_quotes_approved_order"
        ),
        sa.CheckConstraint(
            "cancelled_at IS NULL OR cancelled_at >= created_at", name="ck_quotes_cancelled_order"
        ),
        sa.CheckConstraint(
            "cancellation_reason IS NULL OR "
            "(cancellation_reason = btrim(cancellation_reason) AND cancellation_reason <> '')",
            name="ck_quotes_cancellation_reason_text",
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint("version > 0", name="ck_quotes_version_positive"),
        sa.CheckConstraint(
            "notes IS NULL OR notes = btrim(notes) AND notes <> ''", name="ck_quotes_notes"
        ),
    )
    op.execute("ALTER SEQUENCE quote_number_seq OWNED BY quotes.number")
    op.create_index("ix_quotes_status_valid_until", "quotes", ["status", "valid_until"])
    op.create_index("ix_quotes_status_sent_at", "quotes", ["status", "sent_at"])
    op.create_index("ix_quotes_client_created_id", "quotes", ["client_id", "created_at", "id"])

    op.create_table(
        "quote_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_quote_items"),
        sa.ForeignKeyConstraint(
            ["quote_id"], ["quotes.id"], ondelete="RESTRICT", name="fk_quote_items_quote"
        ),
        sa.UniqueConstraint(
            "quote_id",
            "position",
            name="uq_quote_items_quote_position",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.CheckConstraint(
            "description = btrim(description) AND description <> ''",
            name="ck_quote_items_description",
        ),
        sa.CheckConstraint("position BETWEEN 1 AND 100", name="ck_quote_items_position"),
        sa.CheckConstraint(
            "quantity >= 0.001 AND quantity <= 9999.999", name="ck_quote_items_quantity"
        ),
        sa.CheckConstraint(
            "unit_price >= 0 AND unit_price <= 9999999.99", name="ck_quote_items_unit_price"
        ),
        sa.CheckConstraint(
            "line_total >= 0 AND line_total <= 999999999.99",
            name="ck_quote_items_line_total",
        ),
        sa.CheckConstraint("version > 0", name="ck_quote_items_version_positive"),
    )

    op.create_table(
        "quote_public_access",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("bearer_hash", sa.LargeBinary(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(40), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_quote_public_access"),
        sa.ForeignKeyConstraint(
            ["quote_id"],
            ["quotes.id"],
            ondelete="RESTRICT",
            name="fk_quote_public_access_quote",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_quote_public_access_created_by",
        ),
        sa.UniqueConstraint("bearer_hash", name="uq_quote_public_access_bearer_hash"),
        sa.CheckConstraint(
            "octet_length(bearer_hash) = 32", name="ck_quote_public_access_bearer_hash"
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_quote_public_access_expiry_order"),
        sa.CheckConstraint(
            "(revoked_at IS NULL AND revocation_reason IS NULL) OR "
            "(revoked_at IS NOT NULL AND revocation_reason IS NOT NULL)",
            name="ck_quote_public_access_revocation_pair",
        ),
        sa.CheckConstraint(
            "revocation_reason IS NULL OR revocation_reason IN "
            "('ROTATED','ADMIN_REVOKED','QUOTE_CANCELLED')",
            name="ck_quote_public_access_revocation_reason",
        ),
    )
    op.create_index(
        "uq_quote_public_access_active_quote",
        "quote_public_access",
        ["quote_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index("ix_quote_public_access_expires_at", "quote_public_access", ["expires_at"])

    op.add_column("timeline_events", sa.Column("quote_id", sa.Uuid(), nullable=True))
    op.add_column("timeline_events", sa.Column("actor_public_access_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_timeline_quote",
        "timeline_events",
        "quotes",
        ["quote_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_timeline_actor_public_access",
        "timeline_events",
        "quote_public_access",
        ["actor_public_access_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_timeline_events_quote",
        "timeline_events",
        ["quote_id", "occurred_at", "id"],
        postgresql_where=sa.text("quote_id IS NOT NULL"),
    )
    op.drop_constraint("ck_timeline_events_type_cl03", "timeline_events", type_="check")
    op.create_check_constraint(
        "ck_timeline_events_type_cl04",
        "timeline_events",
        "event_type IN ('user.created','user.disabled','user.enabled',"
        "'user.password_reset','user.password_changed','business.updated',"
        "'client.created','client.updated','client.archived','client.restored',"
        "'equipment.created','equipment.updated','equipment.archived','equipment.restored',"
        "'quote.created','quote.updated','quote.sent','quote.approved','quote.cancelled',"
        "'quote.duplicated','quote.access_rotated','quote.access_revoked')",
    )
    op.drop_constraint("ck_timeline_events_actor_type", "timeline_events", type_="check")
    op.create_check_constraint(
        "ck_timeline_events_actor_type",
        "timeline_events",
        "actor_type IN ('USER','CUSTOMER_QUOTE_LINK','SYSTEM_AUTOMATION')",
    )
    op.drop_constraint("ck_timeline_events_actor", "timeline_events", type_="check")
    op.create_check_constraint(
        "ck_timeline_events_actor",
        "timeline_events",
        "(actor_type = 'USER' AND actor_user_id IS NOT NULL AND "
        "actor_public_access_id IS NULL) OR "
        "(actor_type = 'CUSTOMER_QUOTE_LINK' AND actor_user_id IS NULL AND "
        "actor_public_access_id IS NOT NULL) OR "
        "(actor_type = 'SYSTEM_AUTOMATION' AND actor_user_id IS NULL AND "
        "actor_public_access_id IS NULL)",
    )
    op.drop_constraint("ck_timeline_events_context", "timeline_events", type_="check")
    op.create_check_constraint(
        "ck_timeline_events_context",
        "timeline_events",
        "subject_user_id IS NOT NULL OR business_profile_id IS NOT NULL OR "
        "client_id IS NOT NULL OR quote_id IS NOT NULL",
    )

    op.execute("GRANT SELECT, INSERT ON quotes TO clientops_runtime")
    op.execute(
        "GRANT UPDATE (client_id, status, valid_until, notes, subtotal, total, "
        "commercial_snapshot, sent_at, approved_at, cancelled_at, cancellation_reason, "
        "updated_at, version) ON quotes TO clientops_runtime"
    )
    op.execute("GRANT SELECT, INSERT, DELETE ON quote_items TO clientops_runtime")
    op.execute(
        "GRANT UPDATE (description, quantity, unit_price, line_total, position, updated_at, "
        "version) ON quote_items TO clientops_runtime"
    )
    op.execute("GRANT SELECT, INSERT ON quote_public_access TO clientops_runtime")
    op.execute(
        "GRANT UPDATE (revoked_at, revocation_reason) ON quote_public_access TO clientops_runtime"
    )
    op.execute("GRANT USAGE ON SEQUENCE quote_number_seq TO clientops_runtime")


def downgrade() -> None:
    raise RuntimeError("CL-04 downgrade is destructive; restore a backup or apply a forward fix")
