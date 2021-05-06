import typing
from enum import Enum
from pydantic import validator
from openstates.metadata import lookup
from .common import BaseModel, ORG_ID_RE, PERSON_ID_RE, Link, OtherName


class Parent(str, Enum):
    UPPER = "upper"
    LOWER = "lower"
    JOINT = "legislature"


class Membership(BaseModel):
    name: str
    role: str
    person_id: typing.Optional[str] = None

    @validator("person_id")
    def valid_ocd_person_format(cls, v):
        if isinstance(v, str) and not PERSON_ID_RE.match(v):
            raise ValueError("must match ocd-person/UUID format")
        return v


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

    @validator("jurisdiction")
    def valid_ocd_jurisdiction(cls, v):
        try:
            lookup(jurisdiction_id=v)
        except KeyError:
            raise ValueError(f"invalid jurisdiction_id {v}")
        return v

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
