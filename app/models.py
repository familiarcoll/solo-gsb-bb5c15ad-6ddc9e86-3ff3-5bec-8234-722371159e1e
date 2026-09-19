from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from .filters import FilterError, validate_filter


class SubscriptionIn(BaseModel):
    source: str = Field(min_length=1, max_length=256)
    callback_url: HttpUrl
    filter: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _validate_filter(self) -> "SubscriptionIn":
        if self.filter is not None:
            try:
                validate_filter(self.filter)
            except FilterError as exc:
                raise ValueError(str(exc)) from exc
        return self


class SubscriptionOut(BaseModel):
    id: int
    source: str
    callback_url: str
    next_seq: int
    cursor_seq: int | None
    filter: dict[str, Any] | None = None
    created_at: str

    @field_validator("filter", mode="before")
    @classmethod
    def _parse_filter(cls, value: Any) -> Any:
        # The subscriptions.filter column stores canonical JSON text.
        if isinstance(value, str):
            return json.loads(value)
        return value


class EventIn(BaseModel):
    source: str = Field(min_length=1, max_length=256)
    sequence: int = Field(ge=1)
    event_id: str = Field(min_length=1, max_length=256)
    payload: Any | None = None


class EventAck(BaseModel):
    source: str
    sequence: int
    event_id: str
    duplicate: bool
    queued: int
    skipped: int = 0
    status: str


class DeliveryOut(BaseModel):
    id: int
    subscription_id: int
    source: str
    sequence: int
    event_id: str
    status: str
    attempts: int
    next_attempt_at: str | None
    last_error: str | None
    created_at: str
    updated_at: str


class ReplayResult(BaseModel):
    replayed: int
    delivery_ids: list[int]


class ReplayBulkBody(BaseModel):
    delivery_ids: list[int] = Field(default_factory=list, max_length=1000)
