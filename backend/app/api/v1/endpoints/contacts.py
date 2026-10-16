from __future__ import annotations

import uuid
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AuthenticationError
from app.core.security import oauth2_scheme, verify_token
from app.engines.contact.contact_extractor import ContactExtractor
from app.models.business import Business
from app.models.contact import Contact
from app.models.user import User
from app.schemas.contact import (
    ContactCreate,
    ContactExtractRequest,
    ContactResponse,
    ContactUpdate,
    EmailPatternRequest,
)

router = APIRouter(prefix="/contacts", tags=["contacts"])
_extractor = ContactExtractor()


async def _get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    err = HTTPException(status_code=401, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    try:
        token_data = verify_token(token, expected_type="access")
    except AuthenticationError:
        raise err
    result = await db.execute(select(User).where(User.id == uuid.UUID(token_data.sub)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise err
    return user


@router.get("", response_model=List[ContactResponse])
async def list_contacts(
    business_id: Optional[uuid.UUID] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    q = select(Contact)
    if business_id:
        q = q.where(Contact.business_id == business_id)
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(
    body: ContactCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    biz = await db.get(Business, body.business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")

    contact = Contact(**body.model_dump())
    db.add(contact)
    await db.flush()
    return contact


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    contact = await db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


@router.put("/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: uuid.UUID,
    body: ContactUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    contact = await db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)
    await db.flush()
    return contact


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    contact = await db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    await db.delete(contact)


@router.post("/extract", response_model=List[ContactResponse], status_code=status.HTTP_201_CREATED)
async def extract_contacts(
    body: ContactExtractRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    biz = await db.get(Business, body.business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")

    html = body.html or ""
    extracted = _extractor.extract_from_html(html, str(body.url))

    contacts: list[Contact] = []
    for ec in extracted:
        contact = Contact(
            business_id=body.business_id,
            full_name=ec.full_name,
            first_name=ec.first_name,
            last_name=ec.last_name,
            email=ec.email,
            phone=ec.phone,
            title=ec.title,
            role=ec.role,
            source=ec.source,
            linkedin_url=ec.linkedin_url,
            confidence_score=ec.confidence_score,
            social_profiles=ec.social_profiles or {},
        )
        db.add(contact)
        contacts.append(contact)

    await db.flush()
    return contacts


@router.post("/email-patterns")
async def generate_email_patterns(
    body: EmailPatternRequest,
    current_user: User = Depends(_get_current_user),
):
    patterns = _extractor.generate_email_patterns(body.first_name, body.last_name, body.domain)
    return {"patterns": patterns}
