import typing
from enum import Enum
from pydantic import validator
from .common import (
    BaseModel,
    TimeScoped,
    Link,
    OtherName,
    OtherIdentifier,
    validate_ocd_person,
    validate_url,
    validate_ocd_jurisdiction,
)


class RoleType(str, Enum):
    UPPER = "upper"
    LOWER = "lower"
    JOINT = "legislature"
    GOVERNOR = "governor"
    LT_GOVERNOR = "lt_governor"
    MAYOR = "mayor"


class PersonIdBlock(BaseModel):
    twitter: str = ""
    youtube: str = ""
    instagram: str = ""
    facebook: str = ""


class Party(TimeScoped):
    name: str


class Role(TimeScoped):
    type: RoleType
    district: str
    jurisdiction: str
    end_reason: str

    _validate_jurisdiction = validator("jurisdiction", allow_reuse=True)(validate_ocd_jurisdiction)


class Person(BaseModel):
    id: str
    name: str
    given_name: str = ""
    family_name: str = ""
    middle_name: str = ""
    suffix: str = ""
    gender: str = ""
    email: str = ""
    biography: str = ""
    birth_date: str = ""
    death_date: str = ""
    image: str = ""

    party: list[Party]
    roles: list[Role]

    links: list[Link] = []
    other_names: list[OtherName] = []
    ids: typing.Optional[PersonIdBlock] = None
    other_identifiers: list[OtherIdentifier] = []
    sources: list[Link] = []
    extras: dict = {}

    _validate_person_id = validator("id", allow_reuse=True)(validate_ocd_person)
    _validate_image = validator("image", allow_reuse=True)(validate_url)
