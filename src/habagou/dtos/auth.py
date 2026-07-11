"""Authentication API DTOs."""

from uuid import UUID

from pydantic import BaseModel


class UserDTO(BaseModel):
    id: UUID
    username: str
    display_name: str
    email: str | None = None


class SessionDTO(BaseModel):
    authenticated: bool
    provider: str
    user: UserDTO | None = None
