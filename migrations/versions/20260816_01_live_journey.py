"""Live Journey: live_events table + brands.live_ingest_key

Revision ID: 20260816_01
Revises:
Create Date: 2026-08-16

This is the repo's first migration, but it is deliberately NOT an initial schema
snapshot. The deployed database was built with ``Base.metadata.create_all`` (see
``app.db.init_db`` / ``scripts.dev_init``), so a full snapshot would try to
recreate tables that already exist. This revision only adds what Live Journey
needs, which makes it safe to run against both an existing database and a fresh
one that was create_all'd first.

For the same reason every step is guarded by an inspector check: running
``init_db`` after pulling this branch would already have created the table, and
the Fly release command runs ``alembic upgrade head`` on every deploy.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260816_01"
down_revision = None
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    insp = _inspector()

    if "live_events" not in insp.get_table_names():
        op.create_table(
            "live_events",
            # Identity bigint rather than the UUID string used elsewhere: this is
            # the highest-write table in the schema and random UUID primary keys
            # fragment the index badly under append-heavy load.
            # The sqlite variant matches app.models.BigIntPK: SQLite only
            # auto-increments a column typed exactly INTEGER.
            sa.Column(
                "id",
                sa.BigInteger().with_variant(sa.Integer, "sqlite"),
                autoincrement=True,
                nullable=False,
            ),
            sa.Column("brand_id", sa.String(length=36), nullable=False),
            sa.Column("visitor_id", sa.String(length=64), nullable=False),
            sa.Column("session_id", sa.String(length=64), nullable=True),
            sa.Column("customer_id", sa.String(length=64), nullable=True),
            sa.Column("event_name", sa.String(length=64), nullable=False),
            sa.Column("stage", sa.String(length=32), nullable=False),
            sa.Column("channel", sa.String(length=32), nullable=False),
            sa.Column("path", sa.String(length=512), nullable=True),
            sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        # The only query this table serves: one brand, one time window.
        op.create_index("ix_live_events_brand_ts", "live_events", ["brand_id", "ts"])

    brand_columns = {c["name"] for c in insp.get_columns("brands")}
    if "live_ingest_key" not in brand_columns:
        op.add_column(
            "brands", sa.Column("live_ingest_key", sa.String(length=48), nullable=True)
        )
        op.create_index(
            "ix_brands_live_ingest_key", "brands", ["live_ingest_key"], unique=True
        )


def downgrade() -> None:
    insp = _inspector()

    brand_columns = {c["name"] for c in insp.get_columns("brands")}
    if "live_ingest_key" in brand_columns:
        op.drop_index("ix_brands_live_ingest_key", table_name="brands")
        op.drop_column("brands", "live_ingest_key")

    if "live_events" in insp.get_table_names():
        op.drop_index("ix_live_events_brand_ts", table_name="live_events")
        op.drop_table("live_events")
