import re
import typing
from pydantic import BaseModel as PydanticBaseModel, validator

ORG_ID_RE = re.compile(
    r"^ocd-organization/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
PERSON_ID_RE = re.compile(
    r"^ocd-person/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


class BaseModel(PydanticBaseModel):
    class Config:
        anystr_strip_whitespace = True
        extra = "forbid"

    def to_dict(self):
        # TODO: replace this with first class pydantic support in spatula
        return self.dict()


class Link(BaseModel):
    url: str
    note: typing.Optional[str] = None

    @validator("url")
    def validate_url(cls, v):
        if not v.startswith(("http://", "https://", "ftp://")):
            raise ValueError("URL must start with protocol")
        return v


class OtherName(BaseModel):
    name: str
    start_date: typing.Optional[str] = None
    end_date: typing.Optional[str] = None
    # TODO: add date validators
