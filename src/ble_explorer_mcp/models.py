"""Pydantic models for MCP tool return shapes."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AdvertisedDevice(BaseModel):
    address: str
    name: str | None
    rssi: int | None
    adv_data: dict = Field(default_factory=dict)


class Characteristic(BaseModel):
    uuid: str
    properties: list[str]


class Service(BaseModel):
    uuid: str
    characteristics: list[Characteristic]


class ConnectResult(BaseModel):
    address: str
    services: list[Service]


class DisconnectResult(BaseModel):
    address: str
    disconnected: bool


class ConnectionInfo(BaseModel):
    address: str
    name: str | None
    services_count: int


class ReadResult(BaseModel):
    hex: str
    utf8_or_none: str | None
    int_le_or_none: int | None
    length: int


class WriteResult(BaseModel):
    bytes_written: int


class SubscribeResult(BaseModel):
    subscribed: bool


class Notification(BaseModel):
    address: str
    characteristic_uuid: str
    hex: str
    ts: datetime
