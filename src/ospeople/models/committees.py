import typing
from enum import Enum
from pydantic import validator
from .common import (
    BaseModel,
    ORG_ID_RE,
    Link,
    OtherName,
    validate_ocd_person,
    validate_ocd_jurisdiction,
)


class Parent(str, Enum):
    UPPER = "upper"
    LOWER = "lower"
    JOINT = "legislature"


class Membership(BaseModel):
    name: str
    role: str
    person_id: typing.Optional[str] = None

    _validate_person_id = validator("person_id", allow_reuse=True)(validate_ocd_person)


class ScrapeCommittee(BaseModel):
    name: str
    parent: Parent
    classification: str = "committee"
    sources: typing.List[Link] = []
    links: typing.List[Link] = []
    other_names: typing.List[OtherName] = []
    members: typing.List[Membership] = []

    def add_member(self, name: str, role: str = "member") -> None:
        self.members.append(Membership(name=name, role=role))

    def add_link(self, url: str, note: typing.Optional[str] = None) -> None:
        self.links.append(Link(url=url, note=note))

    def add_source(self, url: str, note: typing.Optional[str] = None) -> None:
        self.sources.append(Link(url=url, note=note))


class Committee(ScrapeCommittee):
    id: str
    jurisdiction: str

    _validate_jurisdiction = validator("jurisdiction", allow_reuse=True)(validate_ocd_jurisdiction)

    @validator("id")
    def valid_ocd_org_format(cls, v):
        if not ORG_ID_RE.match(v):
            raise ValueError("must match ocd-organization/UUID format")
        return v

    def to_dict(self):
        # hack to always have id on top
        return {
            "id": self.id,
            "jurisdiction": self.jurisdiction,
            **super().dict(exclude_defaults=True),
        }
