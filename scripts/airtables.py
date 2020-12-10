from collections import OrderedDict
from dataclasses import dataclass, asdict
import logging
from os import environ, listdir, path
import re
from typing import Dict, List, Optional, Tuple, TypedDict, Union

import airtable
import click

from utils import (
    dump_obj as person_write,
    get_data_root,
    load_yaml_path,
    ocd_uuid,
    person_filepath, 
    reformat_address,
    reformat_phone_number
)


# regex to extract the 'place' value from an
# ocd-jurisdiction string
_REGEX_EXTRACT_PLACE = re.compile(r".*/place:([^\/]+).*")
_REGEX_NON_ENGLISH_CHARS = re.compile(r"[^a-z]+")


def _to_cannonical(s: str) -> str:
    return _REGEX_NON_ENGLISH_CHARS.sub('.', s.lower().strip())


class OpenstatesPersonContact(TypedDict):
    note: str
    address: str
    voice: str

class OpenstatesPersonRole(TypedDict):
    jurisdiction: str
    type: str
    district: Optional[str]
    start_date: Optional[str]
    end_date: Optional[str]

class OpenstatesPersonUrl(TypedDict):
    url: str
    note: Optional[str]


class OpenstatesPerson(TypedDict):
    id: str
    name: str
    given_name: str
    family_name: str
    image: str
    contact_details: List[OpenstatesPersonContact]
    roles: List[OpenstatesPersonRole]
    links: List[OpenstatesPersonUrl]
    sources: List[OpenstatesPersonUrl]

OpenstatesPerson_FieldNames = [
    "id", "name", "given_name", "family_name",
    "image", "contact_details", "roles", "links", "sources", "email"
]

OpenstatesPersonContact_FieldNames = [
    "name",
    "note", 
    "address", 
    "voice"
]

OpenstatesPersonRole_FieldNames = [
    "district", 
    "jurisdiction", 
    "type", 
    "start_date", 
    "end_date"
]

OpenstatesPersonUrl_FieldNames = [
    "url",
    "note"
]

AirtablePersonFieldNames = [
    "state", 
    "govt_branch", 
    "id", 
    "name", 
    "given_name", 
    "family_name", 
    "image", 
    "email"
]

AirtablePersonRoleFieldNames = [
    "state", 
    "govt_branch", 
    "person_id", 
    "name",
    "jurisdiction", 
    "type", 
    "district", 
    "start_date", 
    "end_date"
]

AirtablePersonContactFieldNames = [
    "state", 
    "govt_branch", 
    "person_id", 
    "name",
    "note", 
    "address", 
    "voice"
]

class AirtablePerson(TypedDict):
    state: str
    govt_branch: str
    id: str
    name: str
    given_name: str
    family_name: str
    image: str
    email: str
    role_place: str

class AirtablePersonContact(OpenstatesPersonContact):
    state: str
    govt_branch: str
    person_id: str
    name: str
    place: str

class AirtablePersonRole(OpenstatesPersonRole):
    state: str
    govt_branch: str
    person_id: str
    name: str
    place: str


def _add_airtable_records(
    people_state: str,
    people_govt_branch: str,
    openstates_person: OpenstatesPerson, 
    airtable_people: List[AirtablePerson],
    airtable_people_roles: List[AirtablePersonRole],
    airtable_people_contacts: List[AirtablePersonContact]
):
    """
    creates AirtablePerson (and AirtablePersonRole and AirtablePersonContact) 
    records for one OpenstatesPerson and adds them to the approporiate result lists.
    """
    role_newest, roles_prev = _split_roles(openstates_person.get("roles", []))
    contact_primary, contacts_other = _split_contacts(
        openstates_person.get("contact_details", [])
    )
    source_primary, sources_other = _split_person_urls(
        openstates_person.get("sources", [])
    )
    link_primary, links_other = _split_person_urls(
        openstates_person.get("links", [])
    )
    p = _to_airtable_person(
        people_state, 
        people_govt_branch, 
        openstates_person, 
        role_newest,
        contact_primary,
        source_primary, 
        link_primary
    )
    airtable_people.append(p)
    for r in roles_prev or []:
        airtable_people_roles.append(
            _to_airtable_person_role(people_state, people_govt_branch, p, r)
        )
    for c in contacts_other or []:
        airtable_people_contacts.append(
            _to_airtable_person_contact(people_state, people_govt_branch, p, c)
        )
    # TODO make airtables/types for secondary links and sources
    # as it stands those items would get lost in round trip


def _collect_people_for_sync_down(
    data_root: str,
    people_state: str,
    people_govt_branch: str,
    people_by_id: Dict[str, OpenstatesPerson]
) -> None:
    """
    Collect all openstates people for a given state and govt_branch.

    Args:
        data_root (str): root of openstates people files e.g. ./data
        people_state (str): e.g. 'az' or 'ca'
        people_govt_branch: (str): e.g. 'municipalities' or 'executive'
        result_people_by_id (Dict[str, OpenstatesPerson]): people found
        person_role_records (List[AirtablePersonRole]): non-primary roles (if any) stored here as result
        person_contact_records List[AirtablePersonContact]): non-primary contacts (if any) stored here as result
    """
    people_root = path.join(
        data_root,
        people_state,
        people_govt_branch
    )
    if not path.isdir(people_root):
        return
    for f in listdir(people_root):
        if not f.endswith(".yml"):
            continue
        p = OpenstatesPerson(
            **load_yaml_path(path.join(people_root, f))
        )
        people_by_id[p["id"]] = p


def _collect_people_for_sync_up(
    data_root: str,
    people_state: str,
    people_govt_branch: str,
    person_records: List[AirtablePerson],
    person_role_records: List[AirtablePersonRole],
    person_contact_records: List[AirtablePersonContact]
):
    """
    Collect all openstates people for a given state and govt_branch.

    Args:
        data_root (str): root of openstates people files e.g. ./data
        people_state (str): e.g. 'az' or 'ca'
        people_govt_branch: (str): e.g. 'municipalities' or 'executive'
        person_records (List[AirtablePerson]): AirtablePerson read from the data root stored here as result
        person_role_records (List[AirtablePersonRole]): non-primary roles (if any) stored here as result
        person_contact_records List[AirtablePersonContact]): non-primary contacts (if any) stored here as result
    """
    people_root = path.join(
        data_root,
        people_state, 
        people_govt_branch
    )
    if not path.isdir(people_root):
        return
    for f in sorted(listdir(people_root)):
        if not f.endswith(".yml"):
            continue
        openstates_person = OpenstatesPerson(
            **load_yaml_path(path.join(people_root, f))
        )
        _add_airtable_records(
            people_state, 
            people_govt_branch, 
            openstates_person, 
            person_records, 
            person_role_records,
            person_contact_records
        )


def _extract_place_from_jurisdiction(j: str) -> str:
    """
    Really just because it's a useful thing to display
    in airtables for volunteers 
    (e.g. a column with 'compton' instead of 
    ocd-jurisdiction/country:us/state:ca/place:compton/government')
    """
    m = _REGEX_EXTRACT_PLACE.match(j)
    return "" if not m else m.group(1)


def _is_different_person(a: OpenstatesPerson, b: OpenstatesPerson) -> bool:
    # This is not foolproof since peoples' names can change or
    # require correction, but easier to detect those types of dupes
    # than two completely different people sharing an ocd-person id
    return (
        "name" in a
        and "name" in b
        and a.get("name") != b.get("name")
    )

def _preserve_item_field_order(
    source_list: List[OrderedDict], 
    update_list: List[OrderedDict],
    match_keys: List[str]
) -> List[OrderedDict]:
    """
    We have a list of items to update one of the list props
    in an openstates person (e.g. roles or contact_details).
    If we just overwrite the existing list property though,
    that may create phantom changes 
    (changes just to the order of list-item props),
    so we try to match new items to their preexisting counterparts
    and (if possible) preserve the preexistinglist-item property order.
    of
    """
    result = []
    for update_item in update_list:
        matches = [
            x for x in source_list 
            if all(x.get(k) == update_item.get(k) for k in match_keys)
        ]
        if not matches:
            result.append(update_item)
            continue
        original = matches[0]
        new_item = OrderedDict((k,v) for k, v in original.items())
        for k, v in update_item.items():
            new_item[k] = v
        result.append(new_item)
    return result


def _resolve_states(data_root: str, states: str) -> List[str]:
    """
    Returns a list with either one state (if provided)
    or otherwise all the states (abbrs) under the given data root.
    """
    if states:
        return [states]
    return sorted(
        [s for s in listdir(data_root) if path.isdir(path.join(data_root, s))]
    )


_REGEX_PRIMARY_CONTACT = re.compile(r"[Pp]rimary")
def _split_contacts(
    contacts: List[OpenstatesPersonContact]
) -> Tuple[OpenstatesPersonContact, List[OpenstatesPersonContact]]:
    """
    split (a person's) list of contacts,
    separating out the contact to be considered Primary.
    The Primary Contact will be either:
     - the only contact
     - the contact in a list of multiple contacts with 'note: Primary'
     - the first contact if there are multiple contacts and none marked primary
    """
    if not contacts:
        return (None, [])
    if len(contacts) == 1:
        return contacts[0], []
    primary_ix = 0
    for i, c in enumerate(contacts):
        if _REGEX_PRIMARY_CONTACT.match(c.get("note", '')):
            primary_ix = i
            break
    return (contacts[primary_ix], contacts[:primary_ix]+contacts[primary_ix + 1:])


def _split_roles(
    roles: List[OpenstatesPersonRole]
) -> Tuple[OpenstatesPersonRole, List[OpenstatesPersonRole]]:
    """
    split (a person's) list of roles,
    separating out the role with the latest end date
    (even if it's not current).
    This is to allow us to specially
    with the most common case--a person with just one role.
    And treat role histories as a special case
    """
    if not roles:
        return (None, [])
    sorted_roles = sorted(
        roles, 
        key=lambda x: x.get("end_date", x.get("start_date", '')),
        reverse=True
    )
    return (sorted_roles[0], sorted_roles[1:])

def _split_person_urls(
    urls: List[OpenstatesPersonUrl]
) -> Tuple[OpenstatesPersonUrl, List[OpenstatesPersonUrl]]:
    """
    split (a person's) urls (links, sources)
    separating out the primary from secondary.
    """
    if not urls:
        return (None, [])
    return (urls[0], urls[1:])

def _to_airtable_person(
    people_state: str,
    people_govt_branch: str,
    p: OpenstatesPerson,
    role_newest: OpenstatesPersonRole,
    contact_primary: OpenstatesPersonContact,
    source_primary: OpenstatesPersonUrl,
    link_primary: OpenstatesPersonUrl
) -> AirtablePerson:
    """
    An Airtable person has various properties that an OpenstatesPerson does not, e.g.

     - state and govt_branch (to find the person file again in directory structure)
     - 'primary' role, contact, source, and link

    The reason 'primary' roles, contacts etc. are denormalized
    and stored together with the person in airtable, is that
    it makes it much easier for volunteers to work with,
    and at time of writing this code, the vast majority
    of openstates people have just one role, contact, source, etc. anyway
    """
    return AirtablePerson(
        state=people_state,
        govt_branch=people_govt_branch,
        **{
            k: v for k, v in p.items() if k in AirtablePersonFieldNames
        },
        role_place = (
            _extract_place_from_jurisdiction(role_newest.get("jurisdiction"))
            if role_newest
            else ''
        ),
        # in airtable, prefix all 'primary role' props with 'role_',
        # e.g. role_jurisdiction, role_end_date
        **{ 
            f"role_{k}": v 
            for k, v in (role_newest or {}).items() 
            if k in OpenstatesPersonRole_FieldNames
        },
        # in airtable, prefix all 'primary contact' props with 'contact_',
        # e.g. contact_address, contact_voice
        **{ 
            f"contact_{k}": v 
            for k, v in (contact_primary or {}).items() 
            if k in OpenstatesPersonContact_FieldNames
        },
        **{ 
            f"source_{k}": v 
            for k, v in (source_primary or {}).items() 
            if k in OpenstatesPersonUrl_FieldNames
        },
        **{ 
            f"link_{k}": v 
            for k, v in (link_primary or {}).items() 
            if k in OpenstatesPersonUrl_FieldNames
        }
    )


def _to_airtable_person_contact(
    people_state: str,
    people_govt_branch: str,
    person: AirtablePerson, 
    contact: OpenstatesPersonContact
) -> AirtablePersonContact:
    """
    For openstates people that DO have more than one contact,
    we store all the non-primary contacts normalized
    in another airtable, e.g. openstates_people_contacts
    """
    return AirtablePersonContact(
        state=people_state,
        govt_branch=people_govt_branch,
        person_id = person.get("id"),
        name = person.get("name"),
        **{
            k: v 
            for k, v in contact.items() 
            if k in AirtablePersonContactFieldNames
        },
        place = person.get("role_place", "")
    )

def _to_airtable_person_role(
    people_state: str,
    people_govt_branch: str,
    person: AirtablePerson, 
    role: OpenstatesPersonRole
) -> AirtablePersonRole:
    """
    For openstates people that DO have more than one role,
    we store all but the most recent role normalized
    in another airtable, e.g. openstates_people_roles
    """
    return AirtablePersonRole(
        state=people_state,
        govt_branch=people_govt_branch,
        person_id = person.get("id"),
        name = person.get("name"),
        **{
            k: v 
            for k, v in role.items() 
            if k in AirtablePersonRoleFieldNames
        },
        place = person.get("role_place", "")
    )


def _to_openstates_contact(d: dict, prefix = '') -> OpenstatesPersonContact:
    c = _translate(d, OpenstatesPersonContact_FieldNames, prefix=prefix)
    if "voice" in c:
        c["voice"] = reformat_phone_number(c["voice"])
    if "address" in c:
        c["address"] = reformat_address(c["address"])
    return c


def _to_openstates_role(d: dict, prefix = '') -> OpenstatesPersonRole:
    return _translate(d, OpenstatesPersonRole_FieldNames, prefix=prefix)

    
def _to_openstates_url(d: dict, prefix = '') -> OpenstatesPersonUrl:
    return _translate(d, OpenstatesPersonUrl_FieldNames, prefix=prefix)


def _translate(d: dict, fieldnames: List[str], prefix = '') -> dict:
    """
    Take a data dict (e.g. some component of a person's airtable data)
    and make sure just a specific subset of desired fields are extracted.

    Also translate out field prefixes that were used in airtable
    to denormalize things like 'primary contact' and store it
    together with base person data, e.g contact_address => address
    """
    return OrderedDict(
        (fname, d[f"{prefix}{fname}"])
        for fname in fieldnames 
        if f"{prefix}{fname}" in d
    )


"""
Struct for keeping an OpenstatesPerson
together with their state and govt_branch
"""
@dataclass 
class _OpenstatesPersonStateAndGovtBranch:
    person: OpenstatesPerson
    state: str
    govt_branch: str
    


class OpenstatesAirtables:
    """
    Main class for syncing openstates data up-to/down-from airtable[s].
    """

    def __init__(
        self,
        data_root="./data",
        airtable_api_key='',
        airtable_base='',
        airtable_table_prefix=''
    ):
        self.data_root = path.abspath(data_root)
        self.airtable_api_key = airtable_api_key 
        self.airtable_base = airtable_base
        self.airtable_table_prefix = airtable_table_prefix

    
    def _new_client(self, table_name: str) -> airtable.Airtable:
        return airtable.Airtable(
            self.airtable_base, 
            f"{self.airtable_table_prefix}{table_name}", 
            api_key=self.airtable_api_key
        )


    def _new_people_roles_client(self) -> airtable.Airtable:
        return self._new_client("people_roles")


    def _new_people_client(self) -> airtable.Airtable:
        return self._new_client("people")


    def _new_people_contacts_client(self) -> airtable.Airtable:
        return self._new_client("people_contacts")

    
    def _fetch_people(self) -> Dict[str, _OpenstatesPersonStateAndGovtBranch]:
        """
        Fetch down records from airtable and convert back to OpenstatesPerson objects.
        Return with state and govt_branch info attached to each OpenstatesPerson
        """
        people_by_id: Dict[str, _OpenstatesPersonStateAndGovtBranch] = {}
        a_people: Iterable[AirtablePerson] = self._new_people_client().get_all()
        for a_person in a_people:
            a_person_fields = a_person.get("fields", {})
            sources = []
            primary_source = _to_openstates_url(a_person_fields, "source_")
            if primary_source:
                sources.append(primary_source)
            links = []
            primary_link = _to_openstates_url(a_person_fields, "link_")
            if primary_link:
                links.append(primary_link)
            o_person = OpenstatesPerson(
                **{
                    k:v for k,v in a_person_fields.items() 
                    if k in OpenstatesPerson_FieldNames
                },
                contact_details=[_to_openstates_contact(a_person_fields, "contact_")],
                roles=[_to_openstates_role(a_person_fields, "role_")],
                sources=sources,
                links=links
            )
            id = o_person.get("id", "").split('/')[-1]
            people_by_id[id] = _OpenstatesPersonStateAndGovtBranch(
                person=o_person,
                state=a_person_fields.get("state", ""),
                govt_branch=a_person_fields.get("govt_branch", "")
            )
        return people_by_id
    

    def sync_up(
        self,
        people_state='',
        people_govt_branch='municipalities'
    ) -> None:
        """
        Import openstates data up to airtable.
        Which airtable base, etc. determined by constructor params.

        Args:
            people_state (str): If passed, imports just this state, by default imports all.
            people_govt_branch (str): e.g. 'municipalities' or 'executive'
        """
        person_records: List[AirtablePerson] = []
        person_role_records: List[AirtablePersonRole] = []
        person_contact_records: List[AirtablePersonContact] = []
        for s in _resolve_states(self.data_root, people_state):
            _collect_people_for_sync_up(
                self.data_root,
                s,
                people_govt_branch,
                person_records,
                person_role_records,
                person_contact_records
            )
        if person_records:
            self._new_people_client().batch_insert(person_records)
        if person_role_records:
            self._new_people_roles_client().batch_insert(
                person_role_records
            )
        if person_contact_records:
            self._new_people_contacts_client().batch_insert(
                person_contact_records
            )
    

    def sync_down(self) -> None:
        """
        Sync airtable-openstates data back down to local data files.
        Which airtable base, and location of local data root
        determined by constructor params.
        """
        # get the airtable people records
        # these include all records that were imported to airtable
        # and continue to exist in the base,
        # whether they were updated or not
        airtable_people_by_id = self._fetch_people()
        # we want to do an intelligent sync to the
        # local filesystem records,
        # so first we need the set of distinct (state, govt_branch)
        # pairings for which we have airtable people
        state_govt_branches = set([
            (p.state, p.govt_branch)
            for p in airtable_people_by_id.values()
            if p.state and p.govt_branch
        ])

        def _to_name_and_jurisdiction(person: Union[OpenstatesPerson, AirtablePerson]) -> str:
            jurisdiction = (
                person.get("role_jurisdiction", "")
                if "role_jurisdiction" in person
                else (
                    _split_roles(person.get("roles", []))[0] or {}
                ).get('jurisdiction', '')
                if "roles" in person
                else ""
            )
            return f"{_to_cannonical(person.get('name', ''))}.{jurisdiction}"

        # Having that list of the distinct (state,govt_branch) tuples
        # included in our airtable data, we can collect
        # all the existing people from the local yaml files.
        # We will use these person records to identify
        # a common occurence: that a new person has assumed a role
        # but whoever editted the records didn't clear the old persons ocd-person id
        openstates_people_by_id: Dict[str, OpenstatesPerson] = {}
        # create a map of person-ids where the key is '{state}.{govt_branch}.{cannonical_name}'
        # which we can use for the event of finding if there's already a record for
        # a new/replacement person, i.e. if a previous syncdown created a new ocd-person-id
        # for this person
        person_id_by_name_and_jurisdiction: Dict[str, str] = {}
        for state, govt_branch in state_govt_branches:
            people_batch: Dict[str, OpenstatesPerson] = {}
            _collect_people_for_sync_down(
                self.data_root, state, govt_branch, people_batch
            )
            for id, p in people_batch.items():
                person_id_by_name_and_jurisdiction[
                    _to_name_and_jurisdiction(p)
                ] = id
            openstates_people_by_id.update(people_batch)
        # now we can go through our set of airtable-editted people
        # and sync down the updates to local yaml files
        for id, p in airtable_people_by_id.items():
            try:
                p_before = openstates_people_by_id.get(p.person.get("id", ""), {})
                if _is_different_person(p_before, p.person):
                    # we encountered a person who has an existing ocd-person-id
                    # but a different name from the existing person with that id.
                    # Before we create a new id, we need to check if we already 
                    # did that on a previous syncdown
                    existing_id = person_id_by_name_and_jurisdiction.get(
                        _to_name_and_jurisdiction(p.person),
                        ""
                    )
                    # create a new ocd-person-id,
                    # *only* after making sure there isn't a person
                    # with the same name already in this state/govt branch
                    p.person["id"] = existing_id or ocd_uuid("person")
                    p_before = {}
                pfile = person_filepath(
                    p.person,
                    p.state,
                    p.govt_branch,
                    data_root=self.data_root
                )
                # p_before = load_yaml_path(pfile) if path.isfile(pfile) else {}
                p_synced = OrderedDict((k,v) for k,v in p_before.items())
                for k,v in p.person.items():
                    p_synced[k] = v
                for field, match_key in dict(
                    contact_details=["note"],
                    roles=["jurisdiction", "type", "end_date"]
                ).items():
                    p_synced[field] = _preserve_item_field_order(
                        p_before.get(field, []), 
                        p_synced.get(field, []), 
                        match_key
                    )
                person_write(p_synced, filename=pfile)
            except BaseException as err:
                logging.error(f"failed to update {asdict(p)}")
                logging.exception(str(err), exc_info=True)


@click.group()
def cli():
    pass

@cli.command()
@click.option(
    "--apikey",
    prompt=True,
    default=lambda: environ.get('AIRTABLE_API_KEY', '')
)
@click.option(
    "--base",
    prompt=True,
    default=lambda: environ.get('AIRTABLE_BASE', '')
)
@click.option(
    "--state",
    default=''
)
@click.option(
    "--data",
    prompt=True,
    default=lambda: path.abspath(get_data_root())
)
def syncup(apikey: str, state: str, base: str, data: str):
    OpenstatesAirtables(
        data_root=data,
        airtable_api_key=apikey,
        airtable_base=base,
    ).sync_up(
        people_state=state
    )


@cli.command()
@click.option(
    "--apikey",
    prompt=True,
    default=lambda: environ.get('AIRTABLE_API_KEY', '')
)
@click.option(
    "--base",
    prompt=True,
    default=lambda: environ.get('AIRTABLE_BASE', '')
)
@click.option(
    "--data",
    prompt=True,
    default=lambda: path.abspath(get_data_root())
)
def syncdown(apikey: str, base: str, data: str):
    OpenstatesAirtables(
        data_root=data,
        airtable_api_key=apikey,
        airtable_base=base,
    ).sync_down()


if __name__ == "__main__":
    cli()

