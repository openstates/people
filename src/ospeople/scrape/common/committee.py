import typing
from enum import Enum
from pydantic import BaseModel, validator


class Parent(str, Enum):
    UPPER = "upper"
    LOWER = "lower"
    JOINT = "legislature"


class Link(BaseModel):
    url: str
    note: typing.Optional[str] = None

    @validator("url")
    def validate_url(cls, v):
        if not v.startswith(("http://", "https://", "ftp://")):
            raise ValueError("URL must start with protocol")
        return v

    class Config:
        anystr_strip_whitespace = True
        extra = "forbid"


class Membership(BaseModel):
    name: str
    role: str


class Committee(BaseModel):
    name: str
    parent: Parent
    classification: str = "committee"
    sources: typing.List[Link] = []
    links: typing.List[Link] = []
    other_names: typing.List[Link] = []
    members: typing.List[Membership] = []

    class Config:
        anystr_strip_whitespace = True
        extra = "forbid"

    def add_member(self, name: str, role: str = "member") -> None:
        self.members.append(Membership(name=name, role=role))

    def add_link(self, url: str, note: typing.Optional[str] = None) -> None:
        self.links.append(Link(url=url, note=note))

    def add_source(self, url: str, note: typing.Optional[str] = None) -> None:
        self.sources.append(Link(url=url, note=note))

    def to_dict(self):
        # TODO: replace this with first class pydantic support in spatula
        return self.dict()
