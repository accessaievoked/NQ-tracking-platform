"""Brand + integration routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, get_owned_brand
from app.models import (
    Brand,
    Integration,
    IntegrationProvider,
    IntegrationStatus,
    User,
)
from app.schemas import BrandCreate, BrandDetail, BrandOut, IntegrationOut

router = APIRouter(prefix="/api/brands", tags=["brands"])

# The full set of integrations a brand can connect (mirrors the product).
ALL_PROVIDERS = list(IntegrationProvider)


@router.get("", response_model=list[BrandOut])
def list_brands(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(Brand)
        .filter(Brand.client_id == user.client_id)
        .order_by(Brand.created_at.desc())
        .all()
    )


@router.post("", response_model=BrandDetail, status_code=201)
def create_brand(
    body: BrandCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    brand = Brand(
        client_id=user.client_id,
        name=body.name,
        website=body.website,
        industry=body.industry,
    )
    db.add(brand)
    db.flush()
    # Pre-create integration rows in "not_connected" state for the setup checklist.
    for provider in ALL_PROVIDERS:
        db.add(
            Integration(
                brand_id=brand.id,
                provider=provider,
                status=IntegrationStatus.not_connected,
            )
        )
    db.commit()
    db.refresh(brand)
    return brand


@router.get("/{brand_id}", response_model=BrandDetail)
def get_brand(brand: Brand = Depends(get_owned_brand)):
    return brand


@router.get("/{brand_id}/integrations", response_model=list[IntegrationOut])
def list_integrations(brand: Brand = Depends(get_owned_brand)):
    return brand.integrations
