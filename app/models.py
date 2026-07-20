from datetime import datetime
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    password_encrypted: str
    name: str
    initials: str
    structure: str = ""
    is_admin: bool = False

    assets: list["Asset"] = Relationship(back_populates="owner")


class Asset(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    external_id: str
    label: str
    type: str
    icon: str
    owner_id: int = Field(foreign_key="user.id")

    owner: Optional[User] = Relationship(back_populates="assets")


class Ticket(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(unique=True, index=True)
    client_name: str
    asset_external_id: str
    asset_label: str
    asset_type: str
    status: str = "open"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    user_id: int = Field(foreign_key="user.id")
