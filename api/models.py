from __future__ import annotations

from pydantic import BaseModel


class OwnedPortEntry(BaseModel):
    chassis: str
    port: str
    owner: str
    transmit_state: str
    blocked: bool | None
    cp: bool | None
    dp: bool | None
    utilization: bool | None
    in_session: bool
    session_id: str
    session_name: str
    ixnet_server: str


class OwnedPortsResponse(BaseModel):
    total: int
    ports: list[OwnedPortEntry]


class BlockedPortEntry(BaseModel):
    chassis: str
    port: str
    owner: str
    transmit_state: str
    cp: bool | None
    in_session: bool
    session_id: str
    session_name: str
    ixnet_server: str


class OwnerSummaryEntry(BaseModel):
    owner: str
    ports_hogged: int


class BlockedPortsResponse(BaseModel):
    total_blocked: int
    ports: list[BlockedPortEntry]
    owner_summary: list[OwnerSummaryEntry]
