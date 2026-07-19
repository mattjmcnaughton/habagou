"""Feature-flag API DTOs."""

from uuid import UUID

from pydantic import BaseModel


class FeatureFlagDTO(BaseModel):
    """One code-defined flag: its effective default and per-user override count."""

    key: str
    enabled_default: bool
    override_count: int


class FeatureFlagListDTO(BaseModel):
    flags: list[FeatureFlagDTO]


class FeatureFlagOverrideSetDTO(BaseModel):
    enabled: bool


class FeatureFlagOverrideDTO(BaseModel):
    flag_key: str
    user_id: UUID
    enabled: bool
