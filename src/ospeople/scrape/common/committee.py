import typing
from pydantic import BaseModel, validator


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


class Committee(BaseModel):
    name: str
    classification: str = "committee"
    sources: typing.List[Link] = []
    links: typing.List[Link] = []
    other_names: typing.List[Link] = []
    members: typing.List[str] = []

    class Config:
        anystr_strip_whitespace = True
        extra = "forbid"

    def add_member(self, name: str) -> None:
        self.members.append(name)

    def add_link(self, url: str, note: typing.Optional[str] = None) -> None:
        self.links.append(Link(url=url, note=note))

    def add_source(self, url: str, note: typing.Optional[str] = None) -> None:
        self.sources.append(Link(url=url, note=note))
