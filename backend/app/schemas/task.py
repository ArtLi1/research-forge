import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_type: str
    status: str
    stage: str
    progress: int
    message: str
    resource_type: str | None
    resource_id: uuid.UUID | None
    payload: dict[str, Any]
    error: str | None
    created_at: datetime
    updated_at: datetime
