from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: int
    timestamp: datetime
    client_ip: Optional[str]
    user_id: Optional[str]
    api_key: Optional[str]
    route: str
    method: str
    rule_id: Optional[int]
    limit_type: Optional[str]
    limit_value: Optional[int]
    current_count: Optional[int]

    model_config = {"from_attributes": True}


class AuditQueryParams(BaseModel):
    client_ip: Optional[str] = None
    route: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    page: int = 1
    page_size: int = 50
