"""Pydantic v2 request/response schemas."""
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class ContextBody(BaseModel):
    scope: Literal["category", "merchant", "customer", "trigger"]
    context_id: str
    version: int = Field(ge=1)
    payload: dict[str, Any]
    delivered_at: Optional[str] = None


class TickBody(BaseModel):
    now: str
    available_triggers: list[str] = Field(default_factory=list)


class ReplyBody(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str = "merchant"
    message: str
    received_at: str
    turn_number: int = 1


class Action(BaseModel):
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    send_as: Literal["vera", "merchant_on_behalf"]
    trigger_id: str
    template_name: str
    template_params: list[str] = Field(default_factory=list)
    body: str
    cta: str
    suppression_key: str
    rationale: str


class TickResponse(BaseModel):
    actions: list[Action] = Field(default_factory=list)


class ReplySendResponse(BaseModel):
    action: Literal["send"] = "send"
    body: str
    cta: str
    rationale: str


class ReplyWaitResponse(BaseModel):
    action: Literal["wait"] = "wait"
    wait_seconds: int
    rationale: str


class ReplyEndResponse(BaseModel):
    action: Literal["end"] = "end"
    rationale: str
