"""HTTP request models. Actor is deliberately absent from all write bodies."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FarmRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    intent: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    text: str = Field(min_length=1)


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    revision_hash: str = Field(alias="revisionHash", min_length=1)
    comment: str | None = None


class SimCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str = Field(alias="commandId", min_length=1)
    params: dict[str, object] = Field(default_factory=dict)
