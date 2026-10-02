"""Add CL-02 identity, sessions, security, and business profile schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_identity_sessions_security"
down_revision: str | None = "0001_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "business_profiles",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("trade_name", sa.String(160), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_business_profiles"),
        sa.CheckConstraint("id = 1", name="ck_business_profiles_singleton"),
        sa.CheckConstraint("version > 0", name="ck_business_profiles_version_positive"),
        sa.CheckConstraint(
            "trade_name IS NULL OR trade_name = btrim(trade_name) AND trade_name <> ''",
            name="ck_business_profiles_trade_name",
        ),
        sa.CheckConstraint(
            "phone IS NULL OR phone = btrim(phone) AND phone <> ''",
            name="ck_business_profiles_phone",
        ),
        sa.CheckConstraint(
            "email IS NULL OR email = btrim(email) AND email <> ''",
            name="ck_business_profiles_email",
        ),
        sa.CheckConstraint(
            "address IS NULL OR address = btrim(address) AND address <> ''",
            name="ck_business_profiles_address",
        ),
        sa.CheckConstraint(
            "timezone IS NULL OR timezone = btrim(timezone) AND timezone <> ''",
            name="ck_business_profiles_timezone",
        ),
    )
    op.execute(
        sa.text(
            "INSERT INTO business_profiles "
            "(id, trade_name, phone, email, address, timezone, created_at, updated_at, version) "
            "VALUES (1, NULL, NULL, NULL, NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)"
        )
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("email_normalized", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), nullable=False),
        sa.Column("temporary_password_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email_normalized", name="uq_users_email_normalized"),
        sa.CheckConstraint("role IN ('ADMIN','TECHNICIAN')", name="ck_users_role"),
        sa.CheckConstraint("status IN ('ACTIVE','DISABLED')", name="ck_users_status"),
        sa.CheckConstraint(
            "(must_change_password AND temporary_password_expires_at IS NOT NULL) OR "
            "(NOT must_change_password AND temporary_password_expires_at IS NULL)",
            name="ck_users_temporary_password_state",
        ),
        sa.CheckConstraint("version > 0", name="ck_users_version_positive"),
        sa.CheckConstraint("name = btrim(name) AND name <> ''", name="ck_users_name"),
        sa.CheckConstraint(
            "email_normalized = lower(btrim(email_normalized)) AND "
            "octet_length(email_normalized) <= 254 AND "
            "email_normalized ~ '^[\\x00-\\x7F]+$'",
            name="ck_users_email_normalized",
        ),
        sa.CheckConstraint(
            "password_hash LIKE '$argon2id$%'", name="ck_users_password_hash_argon2id"
        ),
    )
    op.create_index("ix_users_role_status_name_id", "users", ["role", "status", "name", "id"])
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("bearer_hash", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(40), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="RESTRICT", name="fk_sessions_user_id_users"
        ),
        sa.UniqueConstraint("bearer_hash", name="uq_sessions_bearer_hash"),
        sa.CheckConstraint("octet_length(bearer_hash) = 32", name="ck_sessions_bearer_hash"),
        sa.CheckConstraint(
            "created_at <= last_seen_at AND last_seen_at <= absolute_expires_at",
            name="ck_sessions_time_order",
        ),
        sa.CheckConstraint(
            "(revoked_at IS NULL AND revocation_reason IS NULL) OR "
            "(revoked_at IS NOT NULL AND revocation_reason IS NOT NULL)",
            name="ck_sessions_revocation_pair",
        ),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_absolute_expires_at", "sessions", ["absolute_expires_at"])
    op.create_index(
        "ix_sessions_active_candidates",
        "sessions",
        ["user_id", "created_at", "id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_table(
        "rate_limit_buckets",
        sa.Column("rule", sa.String(40), nullable=False),
        sa.Column("key_hash", sa.LargeBinary(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("rule", "key_hash", "window_start", name="pk_rate_limit_buckets"),
        sa.CheckConstraint("octet_length(key_hash) = 32", name="ck_rate_limit_buckets_key_hash"),
        sa.CheckConstraint("count >= 0", name="ck_rate_limit_buckets_count"),
        sa.CheckConstraint("expires_at > window_start", name="ck_rate_limit_buckets_expiry"),
    )
    op.create_index("ix_rate_limit_buckets_expires_at", "rate_limit_buckets", ["expires_at"])
    op.create_table(
        "timeline_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("actor_type", sa.String(30), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("subject_user_id", sa.Uuid(), nullable=True),
        sa.Column("business_profile_id", sa.SmallInteger(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_timeline_events"),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], ondelete="RESTRICT", name="fk_timeline_actor_user"
        ),
        sa.ForeignKeyConstraint(
            ["subject_user_id"], ["users.id"], ondelete="RESTRICT", name="fk_timeline_subject_user"
        ),
        sa.ForeignKeyConstraint(
            ["business_profile_id"],
            ["business_profiles.id"],
            ondelete="RESTRICT",
            name="fk_timeline_business_profile",
        ),
        sa.CheckConstraint(
            "event_type IN ('user.created','user.disabled','user.enabled',"
            "'user.password_reset','user.password_changed','business.updated')",
            name="ck_timeline_events_type_cl02",
        ),
        sa.CheckConstraint(
            "actor_type IN ('USER','SYSTEM_AUTOMATION')", name="ck_timeline_events_actor_type"
        ),
        sa.CheckConstraint(
            "(actor_type = 'USER' AND actor_user_id IS NOT NULL) OR "
            "(actor_type = 'SYSTEM_AUTOMATION' AND actor_user_id IS NULL)",
            name="ck_timeline_events_actor",
        ),
        sa.CheckConstraint(
            "subject_user_id IS NOT NULL OR business_profile_id IS NOT NULL",
            name="ck_timeline_events_context",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object'", name="ck_timeline_events_payload_object"
        ),
        sa.CheckConstraint(
            "octet_length(payload::text) <= 4096", name="ck_timeline_events_payload_size"
        ),
    )
    op.create_index(
        "ix_timeline_events_subject_user",
        "timeline_events",
        ["subject_user_id", "occurred_at", "id"],
        postgresql_where=sa.text("subject_user_id IS NOT NULL"),
    )
    op.create_index(
        "ix_timeline_events_business_profile",
        "timeline_events",
        ["business_profile_id", "occurred_at", "id"],
        postgresql_where=sa.text("business_profile_id IS NOT NULL"),
    )
    op.execute("GRANT SELECT, UPDATE ON business_profiles TO clientops_runtime")
    op.execute("GRANT SELECT, INSERT, UPDATE ON users TO clientops_runtime")
    op.execute("GRANT SELECT, INSERT, UPDATE ON sessions TO clientops_runtime")
    op.execute("GRANT SELECT, INSERT, UPDATE ON rate_limit_buckets TO clientops_runtime")
    op.execute("GRANT SELECT, INSERT ON timeline_events TO clientops_runtime")


def downgrade() -> None:
    raise RuntimeError("CL-02 downgrade is destructive; restore a backup or apply a forward fix")
