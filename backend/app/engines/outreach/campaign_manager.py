from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
import uuid

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class CampaignManager:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_campaign(
        self,
        user_id: uuid.UUID,
        name: str,
        template_id: Optional[uuid.UUID] = None,
        industry_filter: Optional[str] = None,
        min_score: Optional[float] = None,
        max_score: Optional[float] = None,
        description: Optional[str] = None,
    ) -> dict[str, Any]:
        from app.models.outreach import Campaign, CampaignStatus

        campaign = Campaign(
            user_id=user_id,
            name=name,
            template_id=template_id,
            industry_filter=industry_filter,
            min_score=min_score,
            max_score=max_score,
            description=description,
            status=CampaignStatus.draft,
        )
        self.db.add(campaign)
        await self.db.flush()
        return campaign.to_dict()

    async def add_recipients_from_filter(
        self,
        campaign_id: uuid.UUID,
        industry: Optional[str] = None,
        min_score: Optional[float] = None,
        max_score: Optional[float] = None,
        city: Optional[str] = None,
        limit: int = 100,
    ) -> int:
        from app.models.business import Business
        from app.models.contact import Contact
        from app.models.outreach import Campaign, CampaignRecipient, RecipientStatus

        query = select(Business).where(Business.email.isnot(None))
        if industry:
            query = query.where(Business.industry == industry)
        if min_score is not None:
            query = query.where(Business.overall_score >= min_score)
        if max_score is not None:
            query = query.where(Business.overall_score <= max_score)
        if city:
            query = query.where(Business.city == city)
        query = query.limit(limit)

        result = await self.db.execute(query)
        businesses = result.scalars().all()

        count = 0
        for biz in businesses:
            email = biz.email
            if not email:
                contact_q = select(Contact).where(
                    Contact.business_id == biz.id,
                    Contact.email.isnot(None),
                    Contact.is_primary == True,
                )
                contact_result = await self.db.execute(contact_q)
                contact = contact_result.scalar_one_or_none()
                if contact:
                    email = contact.email

            if email:
                recipient = CampaignRecipient(
                    campaign_id=campaign_id,
                    business_id=biz.id,
                    email=email,
                    status=RecipientStatus.pending,
                )
                self.db.add(recipient)
                count += 1

        await self.db.flush()

        await self.db.execute(
            update(Campaign).where(Campaign.id == campaign_id).values(total_recipients=count)
        )

        return count

    async def start_campaign(self, campaign_id: uuid.UUID) -> dict[str, Any]:
        from app.models.outreach import Campaign, CampaignStatus

        result = await self.db.execute(select(Campaign).where(Campaign.id == campaign_id))
        campaign = result.scalar_one_or_none()
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        campaign.status = CampaignStatus.active
        campaign.started_at = datetime.now(timezone.utc)
        await self.db.flush()
        return campaign.to_dict()

    async def pause_campaign(self, campaign_id: uuid.UUID) -> dict[str, Any]:
        from app.models.outreach import Campaign, CampaignStatus

        result = await self.db.execute(select(Campaign).where(Campaign.id == campaign_id))
        campaign = result.scalar_one_or_none()
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        campaign.status = CampaignStatus.paused
        await self.db.flush()
        return campaign.to_dict()

    async def get_campaign_stats(self, campaign_id: uuid.UUID) -> dict[str, Any]:
        from app.models.outreach import Campaign, CampaignRecipient, RecipientStatus

        result = await self.db.execute(select(Campaign).where(Campaign.id == campaign_id))
        campaign = result.scalar_one_or_none()
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        stats = {
            "total": campaign.total_recipients,
            "sent": campaign.sent_count,
            "opened": campaign.opened_count,
            "clicked": campaign.clicked_count,
            "replied": campaign.replied_count,
            "bounced": campaign.bounced_count,
            "open_rate": (campaign.opened_count / max(campaign.sent_count, 1)) * 100,
            "click_rate": (campaign.clicked_count / max(campaign.sent_count, 1)) * 100,
            "reply_rate": (campaign.replied_count / max(campaign.sent_count, 1)) * 100,
        }
        return stats
