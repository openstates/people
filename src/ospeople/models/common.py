import re
import datetime
import typing
from pathlib import Path
import yaml
from pydantic import BaseModel as PydanticBaseModel, validator
from openstates.metadata import lookup

JURISDICTION_RE = re.compile(
    r"ocd-jurisdiction/country:us/(state|district|territory):\w\w/(place|county):[a-z_]+/government"
)
ORG_ID_RE = re.compile(
    r"^ocd-organization/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
PERSON_ID_RE = re.compile(
    r"^ocd-person/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
DATE_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def validate_str_no_newline(v: typing.Any) -> str:
    if isinstance(v, str) and "\n" in v:
        raise ValueError("must be a string without newline")
    return v


def validate_fuzzy_date(v: typing.Any) -> typing.Union[datetime.date, str]:
    if isinstance(v, datetime.date):
        return v
    elif isinstance(v, str) and (v == "" or DATE_RE.match(v)):
        return v
    else:
        raise ValueError("invalid date")


def validate_ocd_person(v: typing.Any) -> str:
    if isinstance(v, str) and not PERSON_ID_RE.match(v):
        raise ValueError("must match ocd-person/UUID format")
    return v


def validate_ocd_jurisdiction(v: typing.Any) -> str:
    try:
        lookup(jurisdiction_id=v)
    except KeyError:
        if not JURISDICTION_RE.match(v):
            raise ValueError(f"invalid jurisdiction_id {v}")
    return v


def validate_url(v: str) -> str:
    if not v.startswith(("http://", "https://", "ftp://")):
        raise ValueError("URL must start with protocol")
    return v


BaseT = typing.TypeVar("BaseT", bound="BaseModel")


class BaseModel(PydanticBaseModel):
    class Config:
        anystr_strip_whitespace = True
        extra = "forbid"
        validate_assignment = True

    def to_dict(self) -> dict[str, typing.Any]:
        # TODO: replace this with first class pydantic support in spatula
        return self.dict()

    @classmethod
    def load_yaml(cls, filename: Path) -> BaseT:
        with open(filename) as file:
            data = yaml.safe_load(file)
            return cls(**data)  # type: ignore


class Link(BaseModel):
    url: str
    note: str = ""

    _validate_note = validator("note", allow_reuse=True)(validate_str_no_newline)
    _validate_url = validator("url", allow_reuse=True)(validate_url)


class TimeScoped(BaseModel):
    start_date: typing.Union[str, datetime.date] = ""
    end_date: typing.Union[str, datetime.date] = ""

    _validate_dates = validator("start_date", "end_date", allow_reuse=True)(validate_fuzzy_date)

    def is_active(self) -> bool:
        date = datetime.datetime.utcnow().date().isoformat()
        return (self.end_date == "" or str(self.end_date) > date) and (
            self.start_date == "" or str(self.start_date) <= date
        )


class OtherName(TimeScoped):
    name: str

    _validate_strs = validator("name", allow_reuse=True)(validate_str_no_newline)


class OtherIdentifier(TimeScoped):
    scheme: str
    identifier: str

    _validate_strs = validator("scheme", "identifier", allow_reuse=True)(validate_str_no_newline)
