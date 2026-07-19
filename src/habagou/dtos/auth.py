"""Authentication API DTOs."""

from uuid import UUID

from pydantic import BaseModel


class UserDTO(BaseModel):
    id: UUID
    username: str
    display_name: str
    email: str | None = None
    # Derived from the email domain at request time (see habagou.authz);
    # admin-only UI (e.g. the AI model picker) keys off this.
    is_admin: bool = False
    # The user's resolved feature-flag map (see services.feature_flags):
    # every registered flag key with its effective on/off state.
    feature_flags: dict[str, bool] = {}


class SessionDTO(BaseModel):
    authenticated: bool
    provider: str
    user: UserDTO | None = None
