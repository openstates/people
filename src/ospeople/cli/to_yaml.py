import typing
import re
import json
import click
import itertools
from pathlib import Path
from collections import defaultdict
from pydantic import BaseModel
from openstates import metadata
from openstates.utils import abbr_to_jid
from ..utils import (
    get_new_filename,
    get_data_path,
    dump_obj,
    ocd_uuid,
)
from ..utils.retire import retire_person, retire_file
from ..models.people import ScrapePerson, Person, Role, Party, ContactDetail, Link


def find_file(leg_id: str, *, state: str = "*") -> Path:
    if leg_id.startswith("ocd-person"):
        leg_id = leg_id.split("/")[1]
    assert len(leg_id) == 36

    if state == "*":
        filedir = get_data_path(".")
        files = list(filedir.glob(f"*/*/*{leg_id}.yml"))
    else:
        filedir = get_data_path(state)
        files = list(filedir.glob(f"*/*{leg_id}.yml"))

    if len(files) == 1:
        return files[0]
    elif len(files) > 1:
        raise ValueError(f"multiple files with same leg_id: {leg_id}")
    else:
        raise FileNotFoundError()


def merge_contact_details(
    old: list[ContactDetail], new: list[ContactDetail]
) -> typing.Optional[typing.List[ContactDetail]]:
    # figure out which office entries are which
    old_offices: dict[str, ContactDetail] = {}
    new_offices: dict[str, ContactDetail] = {}
    offices = []
    update = False

    for office in old:
        note = office.note
        if note not in old_offices:
            old_offices[note] = office
        else:
            raise NotImplementedError(f"extra old {note}")
    for office in new:
        note = office.note
        if note not in new_offices:
            new_offices[note] = office
        else:
            raise NotImplementedError(f"extra old {note}")

    for note_type in sorted(set(old_offices) | set(new_offices)):
        combined = update_office(old_offices.get(note_type), new_offices.get(note_type))
        offices.append(combined)
        if combined != old_offices.get(note_type):
            update = True

    # return all offices if there were any changes
    if update:
        return offices
    else:
        return None


def update_office(
    old_office: typing.Optional[ContactDetail], new_office: typing.Optional[ContactDetail]
) -> ContactDetail:
    """ function returns a copy of old_office updated with values from new if applicable """

    # if only one exists, return that one
    if not old_office and new_office:
        return new_office
    if not new_office and old_office:
        return old_office

    # combine the two
    if new_office and old_office:
        updated_office = old_office.copy()
        for field in updated_office.__fields__.keys():
            oldval = getattr(old_office, field)
            newval = getattr(new_office, field)
            if oldval != newval and newval:
                setattr(updated_office, field, newval)
    return updated_office


class Append:
    def __init__(self, key_name: str, list_item: typing.Any):
        self.key_name = key_name
        self.list_item = list_item

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Append)
            and self.key_name == other.key_name
            and self.list_item == other.list_item
        )

    def __str__(self) -> str:
        return f"{self.key_name}: append {dict(self.list_item)}"

    def __repr__(self) -> str:
        return f"Append({self.key_name}, {self.list_item})"


class Replace:
    def __init__(self, key_name: str, value_one: typing.Any, value_two: typing.Any):
        self.key_name = key_name
        self.value_one = value_one
        self.value_two = value_two

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Replace)
            and self.key_name == other.key_name
            and self.value_one == other.value_one
            and self.value_two == other.value_two
        )

    def __str__(self) -> str:
        return f"{self.key_name}: {self.value_one} => {self.value_two}"

    def __repr__(self) -> str:
        return f"Replace({self.key_name}, {self.value_one}, {self.value_two})"


class ContactDetailsReplace(Replace):
    def __str__(self) -> str:
        def _fmt_cd(cd: ContactDetail) -> str:
            cd_str = f"{cd.note}"
            for key in ("address", "voice", "fax"):
                if val := getattr(cd, key):
                    cd_str += f" {key}={val}"
            return cd_str

        old = "\n\t".join(_fmt_cd(cd) for cd in self.value_one)
        new = "\n\t".join(_fmt_cd(cd) for cd in self.value_two)

        return f"{self.key_name} changed from: \n\t{old}\n  to\n\t{new}"


def compute_merge(
    obj1: BaseModel, obj2: BaseModel, prefix: str = "", keep_both_ids: bool = False
) -> list[typing.Union[Append, Replace]]:
    all_keys = obj1.__fields__.keys()
    changes: list[typing.Union[Append, Replace]] = []

    for key in all_keys:
        key_name = ".".join((prefix, key)) if prefix else key
        val1 = getattr(obj1, key)
        val2 = getattr(obj2, key)

        # special cases first
        if key == "id":
            if val1 != val2 and keep_both_ids:
                # old id stays as id: to keep things sane
                changes.append(
                    Append("other_identifiers", {"scheme": "openstates", "identifier": val2})
                )
        elif key == "name":
            if val1 != val2:
                # new name becomes name, but old name goes into other_names
                changes.append(Append("other_names", {"name": val1}))
                changes.append(Replace("name", val1, val2))
        elif key == "contact_details":
            changed = merge_contact_details(val1, val2)
            if changed:
                changes.append(ContactDetailsReplace("contact_details", val1 or [], changed))
        elif isinstance(val1, list) or isinstance(val2, list):
            if val1 and not val2:
                continue
            elif val2 and not val1:
                changes.append(Replace(key_name, val1, val2))
            else:
                # both have elements, append new to old, leave old intact
                for item in typing.cast(list, val2):
                    if item not in typing.cast(list, val1):
                        changes.append(Append(key_name, item))
        elif isinstance(val1, BaseModel) or isinstance(val2, BaseModel):
            changes.extend(compute_merge(val1, val2, prefix=key_name))
        else:
            # if values both exist and differ, or val1 is empty, do a Replace
            if (val1 and val2 and val1 != val2) or (val1 is None):
                changes.append(Replace(key_name, val1, val2))

    return changes


def roles_equalish(role1: Role, role2: Role) -> bool:
    return (
        role1.type == role2.type
        and role1.jurisdiction == role2.jurisdiction
        and role1.district == role2.district
        and role1.end_date == role2.end_date
        and role1.end_reason == role2.end_reason
    )


def incoming_merge(
    abbr: str, existing_people: list[Person], new_people: list[Person], retirement: str
) -> list[tuple[Person, list[Person]]]:
    unmatched = []

    seats_for_district = {}
    state = metadata.lookup(abbr=abbr)
    for chamber in state.chambers:
        chtype = "legislature" if chamber.chamber_type == "unicameral" else chamber.chamber_type
        seats_for_district[chtype] = {
            district.name: district.num_seats for district in chamber.districts
        }

    # find candidate(s) for each new person
    for new in new_people:
        matched = False
        role_matches = []

        for existing in existing_people:
            name_match = new.name == existing.name
            role_match = False
            for role in existing.roles:
                if role.type == "mayor" or role.type == "governor":
                    continue
                seats = seats_for_district[role.type].get(role.district, 1)
                if roles_equalish(new.roles[0], role) and seats == 1:
                    role_match = True
                    # if they match without start date, copy the start date over so it isn't
                    # altered or otherwise removed in the merge
                    new.roles[0] = role
                    break
            if name_match or role_match:
                matched = interactive_merge(
                    abbr, existing, new, name_match, role_match, retirement
                )

            if matched:
                break

            # if we haven't matched and this was a role match, save this for later
            if role_match:
                role_matches.append(existing)
        else:
            # not matched
            unmatched.append((new, role_matches))

    return unmatched


def copy_new_incoming(abbr: str, new: Person, _type: str) -> None:
    fname = get_new_filename(new.dict())
    oldfname = Path(f"incoming/{abbr}/{_type}/{fname}")
    newfname = f"data/{abbr}/{_type}/{fname}"
    click.secho(f"moving {oldfname} to {newfname}", fg="yellow")
    oldfname.rename(newfname)


def retire(existing: Person, new: Person, retirement: typing.Optional[str] = None) -> None:
    if not retirement:
        retirement = click.prompt("Enter retirement date YYYY-MM-DD")
    person, num = retire_person(existing, typing.cast(str, retirement))
    fname = find_file(existing.id)
    dump_obj(person, filename=fname)
    new_filename = retire_file(fname)
    click.secho(f"moved from {fname} to {new_filename}")


def interactive_merge(
    abbr: str, old: Person, new: Person, name_match: bool, role_match: bool, retirement: str
) -> bool:
    """
    returns True iff a merge was done
    """
    oldfname = find_file(old.id)
    newfname = Path("incoming/{}/legislature/{}".format(abbr, get_new_filename(new.dict())))
    click.secho(" {} {}".format(oldfname, newfname), fg="yellow")

    # simulate difference
    changes = compute_merge(old, new, keep_both_ids=False)

    if not changes:
        click.secho(f" perfect match, removing {newfname}", fg="green")
        newfname.unlink()
        return True

    for change in changes:
        if change.key_name == "name" or change.key_name == "roles":
            click.secho("    " + str(change), fg="red", bold=True)
        else:
            click.echo("    " + str(change))

    ch = "~"
    if name_match and role_match:
        choices = "m"
        # automatically pick merge
        ch = "m"
        # there is one very specific case that this fails in, if someone is beaten
        # by someone with the exact same name, that'll need to be caught manually
    elif name_match:
        choices = "m"
        text = "(m)erge?"
    elif role_match:
        choices = "mr"
        text = f"(m)erge? (r)etire {old.name}"

    while ch not in (choices + "sa"):
        click.secho(text + " (s)kip? (a)bort?", bold=True)
        ch = click.getchar()

    if ch == "a":
        raise SystemExit(-1)
    elif ch == "m":
        merged = merge_people(old, new, keep_both_ids=False)
        dump_obj(merged, filename=oldfname)
        click.secho(" merged.", fg="green")
        newfname.unlink()
    elif ch == "r":
        copy_new_incoming(abbr, new, "legislature")
        retire(old, new, retirement)
    elif ch == "s":
        return False

    return True


def merge_people(old: Person, new: Person, keep_both_ids: bool = False) -> Person:
    """
    Function to merge two people objects.

    keep_both_ids
        Should be set to True iff people have been imported before.
        If we're dealing with an election, it should be set to false since the new ID
        hasn't been published anywhere yet.
    """
    changes = compute_merge(
        old,
        new,
        keep_both_ids=keep_both_ids,
    )

    for change in changes:
        if isinstance(change, Replace):
            keys = change.key_name.split(".")

            # recursively set the value based on dotted key
            temp_obj = old
            for key in keys[:-1]:
                temp_obj = getattr(temp_obj, key)
            setattr(temp_obj, keys[-1], change.value_two)
        if isinstance(change, Append):
            getattr(old, change.key_name).append(change.list_item)
    return old


PHONE_RE = re.compile(
    r"""^
                      \D*(1?)\D*                                # prefix
                      (\d{3})\D*(\d{3})\D*(\d{4}).*?             # main 10 digits
                      (?:(?:ext|Ext|EXT)\.?\s*\s*(\d{1,4}))?    # extension
                      $""",
    re.VERBOSE,
)


def reformat_phone_number(phone: str) -> str:
    match = PHONE_RE.match(phone)
    if match:
        groups = match.groups()

        ext = groups[-1]
        if ext:
            ext = f" ext. {ext}"
        else:
            ext = ""

        if not groups[0]:
            groups = groups[1:-1]
        else:
            groups = groups[:-1]
        return "-".join(groups) + ext
    else:
        return phone


def reformat_address(address: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\s*\n\s*", ";", address))


def process_pupa_scrape_dir(
    input_dir: Path, output_dir: Path, jurisdiction_id: str
) -> list[Person]:
    new_people = []
    person_memberships = defaultdict(list)

    # collect memberships
    for filename in input_dir.glob("membership_*.json"):
        with open(filename) as f:
            membership = json.load(f)

        if membership["person_id"].startswith("~"):
            raise ValueError(membership)
        person_memberships[membership["person_id"]].append(membership)

    # process people
    for filename in input_dir.glob("person_*.json"):
        with open(filename) as f:
            person = json.load(f)

        scrape_id = person["_id"]
        person["memberships"] = person_memberships[scrape_id]
        scrape_person = process_pupa_person(person, jurisdiction_id)
        person = Person(**scrape_person.dict(), id=ocd_uuid("person"))
        new_people.append(person)

        dump_obj(person, output_dir=output_dir)

    return new_people


def process_pupa_person(person: dict, jurisdiction_id: str) -> ScrapePerson:
    optional_keys = (
        "image",
        "gender",
        "biography",
        "given_name",
        "family_name",
        "birth_date",
        "death_date",
        "national_identity",
        "summary",
        # maybe post-process these?
        "other_names",
    )

    result = ScrapePerson(
        name=person["name"],
        roles=[],
        links=[Link(url=link["url"], note=link["note"]) for link in person["links"]],
        sources=[Link(url=link["url"], note=link["note"]) for link in person["sources"]],
    )

    contact_details: defaultdict[str, defaultdict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    email = None
    for detail in person["contact_details"]:
        value = detail["value"]
        if detail["type"] in ("voice", "fax"):
            value = reformat_phone_number(value)
        elif detail["type"] == "address":
            value = reformat_address(value)
        elif detail["type"] == "email":
            email = value
            continue
        contact_details[detail["note"]][detail["type"]] = value

    if email:
        result.email = email
    result.contact_details = [
        ContactDetail(note=key, **val) for key, val in contact_details.items()
    ]

    for membership in person["memberships"]:
        organization_id = membership["organization_id"]
        if organization_id.startswith("~"):
            org = json.loads(organization_id[1:])
            if org["classification"] in ("upper", "lower", "legislature"):
                post = json.loads(membership["post_id"][1:])["label"]
                result.roles = [
                    Role(
                        type=org["classification"],
                        district=str(post),
                        jurisdiction=jurisdiction_id,
                    )
                ]
            elif org["classification"] == "party":
                result.party = [Party(name=org["name"])]

    for key in optional_keys:
        if val := person.get(key):
            setattr(result, key, val)

    # promote some extras where appropriate
    extras = person.get("extras", {}).copy()
    for key in person.get("extras", {}).keys():
        if key in optional_keys:
            setattr(result, key, extras.pop(key))
    if extras:
        result.extras = extras

    if person.get("identifiers"):
        result.other_identifiers = person["identifiers"]

    return result


@click.command()  # pragma: no cover
@click.argument("input_dir")
@click.option(
    "--retirement",
    default=None,
    help="Set retirement date for all people marked retired (in incoming mode).",
)
def main(input_dir: str, retirement: str) -> None:
    """
    Convert scraped JSON in INPUT_DIR to YAML files for this repo.

    Will put data into incoming/ directory for usage with merge.py's --incoming option.
    """

    # abbr is last piece of directory name
    abbr = ""
    for piece in input_dir.split("/")[::-1]:
        if piece:
            abbr = piece
            break

    jurisdiction_id = abbr_to_jid(abbr)

    output_dir = get_data_path(abbr)
    incoming_dir = Path(str(output_dir).replace("data", "incoming")) / "legislature"
    assert "incoming" in str(incoming_dir)

    try:
        incoming_dir.mkdir(parents=True)
    except FileExistsError:
        for file in incoming_dir.glob("*.yml"):
            file.unlink()

    new_people = process_pupa_scrape_dir(Path(input_dir), incoming_dir, jurisdiction_id)

    existing_people: list[Person] = []
    directory = get_data_path(abbr)
    for filename in itertools.chain(
        directory.glob("legislature/*.yml"),
        directory.glob("retired/*.yml"),
    ):
        existing_people.append(Person.load_yaml(filename))

    click.secho(f"analyzing {len(existing_people)} existing people and {len(new_people)} incoming")

    unmatched = incoming_merge(abbr, existing_people, new_people, retirement)
    click.secho(f"{len(unmatched)} people were unmatched")


if __name__ == "__main__":
    main()
