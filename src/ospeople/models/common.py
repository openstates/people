import re
import typing
from pydantic import BaseModel as PydanticBaseModel, validator
from openstates.metadata import lookup


ORG_ID_RE = re.compile(
    r"^ocd-organization/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
PERSON_ID_RE = re.compile(
    r"^ocd-person/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def validate_ocd_person(v):
    if isinstance(v, str) and not PERSON_ID_RE.match(v):
        raise ValueError("must match ocd-person/UUID format")
    return v


def validate_ocd_jurisdiction(v):
    try:
        lookup(jurisdiction_id=v)
    except KeyError:
        raise ValueError(f"invalid jurisdiction_id {v}")
    return v


def validate_url(v):
    if not v.startswith(("http://", "https://", "ftp://")):
        raise ValueError("URL must start with protocol")
    return v


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

    _validate_url = validator("url", allow_reuse=True)(validate_url)


class OtherName(BaseModel):
    name: str
    start_date: typing.Optional[str] = None
    end_date: typing.Optional[str] = None
    # TODO: add date validators
