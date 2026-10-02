"""Add CL-03 clients, equipment, and client timeline context."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_clients_equipment"
down_revision: str | None = "0002_identity_sessions_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("notes", sa.String(5000), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_clients"),
        sa.CheckConstraint("name = btrim(name) AND name <> ''", name="ck_clients_name"),
        sa.CheckConstraint(
            "phone IS NULL OR phone = btrim(phone) AND phone <> ''", name="ck_clients_phone"
        ),
        sa.CheckConstraint(
            "email IS NULL OR email = btrim(email) AND email <> ''", name="ck_clients_email"
        ),
        sa.CheckConstraint(
            "address IS NULL OR address = btrim(address) AND address <> ''",
            name="ck_clients_address",
        ),
        sa.CheckConstraint(
            "notes IS NULL OR notes = btrim(notes) AND notes <> ''", name="ck_clients_notes"
        ),
        sa.CheckConstraint("status IN ('ACTIVE','ARCHIVED')", name="ck_clients_status"),
        sa.CheckConstraint(
            "(status = 'ACTIVE' AND archived_at IS NULL) OR "
            "(status = 'ARCHIVED' AND archived_at IS NOT NULL)",
            name="ck_clients_archive_state",
        ),
        sa.CheckConstraint("version > 0", name="ck_clients_version_positive"),
    )
    op.create_index("ix_clients_status_name_id", "clients", ["status", "name", "id"])
    op.create_index("ix_clients_created_at", "clients", ["created_at"])

    op.create_table(
        "equipment",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("brand", sa.String(120), nullable=True),
        sa.Column("model", sa.String(120), nullable=True),
        sa.Column("serial_number", sa.String(100), nullable=True),
        sa.Column("location_description", sa.String(300), nullable=True),
        sa.Column("notes", sa.String(5000), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_equipment"),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["clients.id"],
            ondelete="RESTRICT",
            name="fk_equipment_client_id_clients",
        ),
        sa.UniqueConstraint("id", "client_id", name="uq_equipment_id_client_id"),
        sa.CheckConstraint("name = btrim(name) AND name <> ''", name="ck_equipment_name"),
        sa.CheckConstraint(
            "brand IS NULL OR brand = btrim(brand) AND brand <> ''", name="ck_equipment_brand"
        ),
        sa.CheckConstraint(
            "model IS NULL OR model = btrim(model) AND model <> ''", name="ck_equipment_model"
        ),
        sa.CheckConstraint(
            "serial_number IS NULL OR serial_number = btrim(serial_number) AND serial_number <> ''",
            name="ck_equipment_serial_number",
        ),
        sa.CheckConstraint(
            "location_description IS NULL OR location_description = btrim(location_description) "
            "AND location_description <> ''",
            name="ck_equipment_location_description",
        ),
        sa.CheckConstraint(
            "notes IS NULL OR notes = btrim(notes) AND notes <> ''", name="ck_equipment_notes"
        ),
        sa.CheckConstraint("status IN ('ACTIVE','ARCHIVED')", name="ck_equipment_status"),
        sa.CheckConstraint(
            "(status = 'ACTIVE' AND archived_at IS NULL) OR "
            "(status = 'ARCHIVED' AND archived_at IS NOT NULL)",
            name="ck_equipment_archive_state",
        ),
        sa.CheckConstraint("version > 0", name="ck_equipment_version_positive"),
    )
    op.create_index(
        "ix_equipment_client_status_name_id", "equipment", ["client_id", "status", "name", "id"]
    )

    op.add_column("timeline_events", sa.Column("client_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_timeline_client",
        "timeline_events",
        "clients",
        ["client_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_timeline_events_client",
        "timeline_events",
        ["client_id", "occurred_at", "id"],
        postgresql_where=sa.text("client_id IS NOT NULL"),
    )
    op.drop_constraint("ck_timeline_events_type_cl02", "timeline_events", type_="check")
    op.create_check_constraint(
        "ck_timeline_events_type_cl03",
        "timeline_events",
        "event_type IN ('user.created','user.disabled','user.enabled',"
        "'user.password_reset','user.password_changed','business.updated',"
        "'client.created','client.updated','client.archived','client.restored',"
        "'equipment.created','equipment.updated','equipment.archived','equipment.restored')",
    )
    op.drop_constraint("ck_timeline_events_context", "timeline_events", type_="check")
    op.create_check_constraint(
        "ck_timeline_events_context",
        "timeline_events",
        "subject_user_id IS NOT NULL OR business_profile_id IS NOT NULL OR client_id IS NOT NULL",
    )

    op.execute("GRANT SELECT, INSERT ON clients TO clientops_runtime")
    op.execute(
        "GRANT UPDATE (name, phone, email, address, notes, status, archived_at, "
        "updated_at, version) "
        "ON clients TO clientops_runtime"
    )
    op.execute("GRANT SELECT, INSERT ON equipment TO clientops_runtime")
    op.execute(
        "GRANT UPDATE (name, brand, model, serial_number, location_description, notes, status, "
        "archived_at, updated_at, version) ON equipment TO clientops_runtime"
    )


def downgrade() -> None:
    raise RuntimeError("CL-03 downgrade is destructive; restore a backup or apply a forward fix")
