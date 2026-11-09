from typing import Literal
from uuid import UUID

from pydantic import BaseModel

SearchEntityType = Literal[
    "customer",
    "object",
    "employee",
    "document",
    "contract",
    "shift",
    "task",
    "incident",
    "key",
    "owks_event",
]


class SearchResult(BaseModel):
    id: UUID
    type: SearchEntityType
    title: str
    reference: str


class SearchPage(BaseModel):
    items: list[SearchResult]
    total: int
    limit: int
    offset: int
