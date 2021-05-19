import re
import typing
import datetime
from enum import Enum
from pydantic import validator, root_validator
from .common import (
    BaseModel,
    TimeScoped,
    Link,
    OtherName,
    OtherIdentifier,
    validate_ocd_person,
    validate_url,
    validate_fuzzy_date,
    validate_ocd_jurisdiction,
    validate_str_no_newline,
)

# can only have one of these at a time
MAJOR_PARTIES = ("Democratic", "Republican", "Independent")

SUFFIX_RE = re.compile(r"(iii?)|(i?v)|((ed|ph|m|o)\.?d\.?)|([sj]r\.?)|(esq\.?)", re.I)
PHONE_RE = re.compile(r"^(1-)?\d{3}-\d{3}-\d{4}( ext. \d+)?$")


def validate_phone(val: str) -> str:
    if val and not PHONE_RE.match(val):
        raise ValueError("invalid phone number")
    return val


class PartyName(str, Enum):
    DEM = "Democratic"
    GREEN = "Green"
    IND = "Independent"
    LIB = "Libertarian"
    NP = "Nonpartisan"
    PROG = "Progressive"
    REP = "Republican"
    MN_DFL = "Democratic-Farmer-Labor"
    VT_DEM_PROG = "Democratic/Progressive"
    VT_PROG_DEM = "Progressive/Democratic"
    VT_REP_DEM = "Republican/Democratic"
    TN_CC_REP = "Carter County Republican"
    NY_INDEPENDENCE = "Independence"
    PR_PIP = "Partido Independentista Puertorrique\xF1o"
    PR_PNP = "Partido Nuevo Progresista"
    PR_PPD = "Partido Popular Democr\xE1tico"
    PR_PD = "Proyecto Dignidad"
    PR_MVC = "Movimiento Victoria Ciudadana"


class RoleType(str, Enum):
    UPPER = "upper"
    LOWER = "lower"
    JOINT = "legislature"
    GOVERNOR = "governor"
    LT_GOVERNOR = "lt_governor"
    MAYOR = "mayor"
    SOS = "secretary of state"
    CHIEF_ELECTION_OFFICER = "chief election officer"


LEGISLATIVE_ROLES = (
    RoleType.UPPER,
    RoleType.LOWER,
    RoleType.JOINT,
)
EXECUTIVE_ROLES = (
    RoleType.GOVERNOR,
    RoleType.LT_GOVERNOR,
    RoleType.MAYOR,
    RoleType.CHIEF_ELECTION_OFFICER,
    RoleType.SOS,
)


class ContactType(str, Enum):
    DISTRICT = "District Office"
    CAPITOL = "Capitol Office"
    PRIMARY = "Primary Office"


class PersonIdBlock(BaseModel):
    twitter: str = ""
    youtube: str = ""
    instagram: str = ""
    facebook: str = ""

    @validator("*")
    def validate_social(cls, val: str) -> str:
        validate_str_no_newline(val)
        if val.startswith(("http://", "https://", "@")):
            raise ValueError("invalid social media account name, drop URL or @")
        return val


class Party(TimeScoped):
    name: PartyName

    _validate_strs = validator("name", allow_reuse=True)(validate_str_no_newline)


class Role(TimeScoped):
    type: RoleType
    jurisdiction: str
    district: typing.Optional[str] = None
    end_reason: str = ""  # note: this field not imported to db

    _validate_strs = validator("district", "end_reason", allow_reuse=True)(validate_str_no_newline)
    _validate_jurisdiction = validator("jurisdiction", allow_reuse=True)(validate_ocd_jurisdiction)

    @root_validator
    def check_conditional_required_fields(
        cls, values: dict[str, typing.Any]
    ) -> dict[str, typing.Any]:
        # executives require end_date, everyone else requires a district & party
        office_type = values.get("type")
        end_date = values.get("end_date")
        district = values.get("district")
        if office_type in LEGISLATIVE_ROLES and not district:
            raise ValueError("district is required for legislative roles")
        if office_type in EXECUTIVE_ROLES and not end_date:
            raise ValueError("end_date is required for executive roles")
        return values


class ContactDetail(BaseModel):
    note: ContactType
    address: str = ""
    voice: str = ""
    fax: str = ""

    _validate_strs = validator("address", allow_reuse=True)(validate_str_no_newline)
    _validate_phones = validator("voice", "fax", allow_reuse=True)(validate_phone)

    @root_validator
    def check_have_at_least_one_value(cls, values: dict[str, typing.Any]) -> dict[str, typing.Any]:
        if not any((values.get("address"), values.get("voice"), values.get("fax"))):
            raise ValueError("must have at least one valid contact type for the office")
        return values


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
    birth_date: typing.Union[datetime.date, str] = ""
    death_date: typing.Union[datetime.date, str] = ""
    image: str = ""

    party: list[Party] = []
    roles: list[Role]

    contact_details: list[ContactDetail] = []
    links: list[Link] = []
    other_names: list[OtherName] = []
    ids: PersonIdBlock = PersonIdBlock()
    other_identifiers: list[OtherIdentifier] = []
    sources: list[Link] = []
    extras: dict = {}

    @root_validator
    def check_active_party(cls, values: dict[str, typing.Any]) -> dict[str, typing.Any]:
        require_party = False
        for role in values.get("roles", []):
            if role.is_active() and role.type in LEGISLATIVE_ROLES:
                require_party = True

        active_parties = []
        for party in values.get("party", []):
            if party.is_active():
                active_parties.append(party.name)

        if len(active_parties) == 0 and require_party:
            raise ValueError("no active parties")
        elif len(active_parties) > 1:
            if len([party for party in active_parties if party in MAJOR_PARTIES]) > 1:
                raise ValueError(f"multiple active party memberships: {active_parties}")
            # TODO: warn again
            # else:
            #     self.warnings[person.print_filename].append(
            #         f"multiple active party memberships {active_parties}"
            #     )

        return values

    @validator("name")
    def no_bad_comma(self, val: str) -> str:
        pieces = val.split(",")
        if len(pieces) > 2:
            raise ValueError("too many commas, check if name is mangled")
        elif len(pieces) == 2 and not SUFFIX_RE.findall(pieces[1]):
            raise ValueError("invalid comma")
        return val

    _validate_person_id = validator("id", allow_reuse=True)(validate_ocd_person)
    _validate_dates = validator("birth_date", "death_date", allow_reuse=True)(validate_fuzzy_date)
    _validate_strings_no_newline = validator(
        # only biography is allowed newlines
        "name",
        "given_name",
        "family_name",
        "given_name",
        "middle_name",
        "email",
        "suffix",
        "gender",
        allow_reuse=True,
    )(validate_str_no_newline)
    _validate_image = validator("image", allow_reuse=True)(validate_url)
