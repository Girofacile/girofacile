"""Private, versioned multi-route previews; no operational routes until confirmation."""
from datetime import datetime
from .core.clock import utc_now
from sqlalchemy import ForeignKey, JSON, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

class FleetPlan(Base):
    __tablename__='fleet_plans'
    id: Mapped[int]=mapped_column(primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    actor: Mapped[str]=mapped_column(String(80))
    version: Mapped[int]=mapped_column(default=1)
    status: Mapped[str]=mapped_column(String(30),default='preview')
    configuration: Mapped[dict]=mapped_column(JSON)
    result: Mapped[dict]=mapped_column(JSON)
    route_ids: Mapped[list]=mapped_column(JSON,default=list)
    created_at: Mapped[datetime]=mapped_column(DateTime,default=utc_now)
