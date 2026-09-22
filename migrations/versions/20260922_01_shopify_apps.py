"""Per-brand Shopify apps: shopify_apps table + brands.shopify_app_id

Revision ID: 20260922_01
Revises: 20260816_01
Create Date: 2026-09-22

Custom-distribution Shopify apps can only be installed on the one store they
were made for, so each client store gets its own app. Brands with no app keep
using the default one from SHOPIFY_API_KEY / SHOPIFY_API_SECRET.

Guarded by inspector checks like the previous revision: the Fly release command
runs this on every deploy, and a database built with create_all may already
have the table and column.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260922_01"
down_revision = "20260816_01"
branch_labels = None
depends_on = None

FK_NAME = "fk_brands_shopify_app_id_shopify_apps"
IX_NAME = "ix_brands_shopify_app_id"


def _inspector():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    insp = _inspector()

    if "shopify_apps" not in insp.get_table_names():
        op.create_table(
            "shopify_apps",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False, unique=True),
            sa.Column("client_id", sa.String(length=100), nullable=False, unique=True),
            sa.Column("encrypted_client_secret", sa.Text(), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
        )

    insp = _inspector()
    brand_columns = {c["name"] for c in insp.get_columns("brands")}
    if "shopify_app_id" not in brand_columns:
        op.add_column(
            "brands", sa.Column("shopify_app_id", sa.String(length=36), nullable=True)
        )

    insp = _inspector()
    if IX_NAME not in {ix["name"] for ix in insp.get_indexes("brands")}:
        op.create_index(IX_NAME, "brands", ["shopify_app_id"])

    fks = insp.get_foreign_keys("brands")
    has_fk = any(
        fk.get("referred_table") == "shopify_apps"
        and fk.get("constrained_columns") == ["shopify_app_id"]
        for fk in fks
    )
    if not has_fk:
        op.create_foreign_key(
            FK_NAME, "brands", "shopify_apps",
            ["shopify_app_id"], ["id"], ondelete="SET NULL",
        )


def downgrade() -> None:
    insp = _inspector()
    for fk in insp.get_foreign_keys("brands"):
        if fk.get("referred_table") == "shopify_apps" and fk.get("name"):
            op.drop_constraint(fk["name"], "brands", type_="foreignkey")
    if IX_NAME in {ix["name"] for ix in insp.get_indexes("brands")}:
        op.drop_index(IX_NAME, table_name="brands")
    if "shopify_app_id" in {c["name"] for c in insp.get_columns("brands")}:
        op.drop_column("brands", "shopify_app_id")
    if "shopify_apps" in insp.get_table_names():
        op.drop_table("shopify_apps")
