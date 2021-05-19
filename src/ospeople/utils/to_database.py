import typing
import datetime
from functools import lru_cache
import click
from openstates import metadata
from ..utils import legacy_districts
from ..models.people import MAJOR_PARTIES, Person, PartyName


DataDict = dict[str, typing.Any]
# TODO: whenever Django typed replace these
DjangoModel = typing.Any
DjangoModelInstance = typing.Any


class CancelTransaction(Exception):
    pass


@lru_cache(128)
def cached_lookup(ModelCls: DjangoModel, **kwargs: str) -> DjangoModelInstance:
    # return ModelCls.objects.get(**kwargs)
    m = ModelCls.objects.get(**kwargs)
    return m


def update_subobjects(
    person: DjangoModelInstance,
    fieldname: str,
    objects: list[DataDict],
    read_manager: typing.Any = None,
) -> bool:
    """ returns True if there are any updates """
    # we need the default manager for this field in case we need to do updates
    manager = getattr(person, fieldname)

    # if a read_manager is passed, we'll use that for all read operations
    # this is used for DjangoPerson.memberships to ensure we don't wipe out committee memberships
    if read_manager is None:
        read_manager = manager

    current_count = read_manager.count()
    updated = False

    # if counts differ, we need to do an update for sure
    if current_count != len(objects):
        updated = True

    # check if all objects exist
    if not updated:
        qs = read_manager
        for obj in objects:
            qs = qs.exclude(**obj)

        if qs.exists():
            updated = True

    # if there's been an update, wipe the old & insert the new
    if updated:
        if current_count:
            read_manager.all().delete()
        for obj in objects:
            manager.create(**obj)
        # save to bump updated_at timestamp
        person.save()

    return updated


def get_update_or_create(
    ModelCls: DjangoModel, data: dict, lookup_keys: list[str]
) -> tuple[DjangoModelInstance, bool, bool]:
    updated = created = False
    kwargs = {k: data[k] for k in lookup_keys}
    try:
        obj = ModelCls.objects.get(**kwargs)
        for field, value in data.items():
            # special case datetime since comparisons won't work between str/datetime
            if isinstance(value, datetime.date):
                value = str(value)
            if getattr(obj, field) != value:
                setattr(obj, field, value)
                updated = True
        if updated:
            obj.save()
    except ModelCls.DoesNotExist:
        obj = ModelCls.objects.create(**data)
        created = True
    return obj, created, updated


def load_person(data: Person) -> tuple[bool, bool]:
    # import has to be here so that Django is set up
    from openstates.data.models import Organization, Post
    from openstates.data.models import Person as DjangoPerson

    fields = dict(
        id=data.id,
        name=data.name,
        given_name=data.given_name,
        family_name=data.family_name,
        gender=data.gender,
        email=data.email,
        biography=data.biography,
        birth_date=data.birth_date,
        death_date=data.death_date,
        image=data.image,
        extras=data.extras,
    )
    person, created, updated = get_update_or_create(DjangoPerson, fields, ["id"])

    updated |= update_subobjects(person, "other_names", [n.dict() for n in data.other_names])
    updated |= update_subobjects(person, "links", [n.dict() for n in data.links])
    updated |= update_subobjects(person, "sources", [n.dict() for n in data.sources])

    identifiers = []
    for scheme, value in data.ids.dict().items():
        if value:
            identifiers.append({"scheme": scheme, "identifier": value})
    for identifier in data.other_identifiers:
        identifiers.append({"scheme": identifier.scheme, "identifier": identifier.identifier})
    updated |= update_subobjects(person, "identifiers", identifiers)

    contact_details = []
    for cd in data.contact_details:
        for field in ("address", "voice", "fax"):
            if value := getattr(cd, field):
                contact_details.append({"note": cd.note, "type": field, "value": value})
    updated |= update_subobjects(person, "contact_details", contact_details)

    memberships = []
    primary_party = ""
    current_jurisdiction_id = None
    current_role = None
    for party in data.party:
        party_name = party.name
        try:
            org = cached_lookup(Organization, classification="party", name=party.name)
        except Organization.DoesNotExist:
            click.secho(f"no such party {party.name}", fg="red")
            raise CancelTransaction()
        memberships.append(
            {
                "organization": org,
                "start_date": party.start_date,
                "end_date": party.end_date,
            }
        )
        if party.is_active():
            if primary_party in MAJOR_PARTIES and party_name in MAJOR_PARTIES:
                raise ValueError(f"two primary parties for ({data.name} {data.id})")
            elif primary_party in MAJOR_PARTIES:
                # already set correct primary party, so do nothing
                pass
            else:
                primary_party = party_name
    for role in data.roles:
        if role.type == "mayor":
            role_name = "Mayor"
            org_type = "government"
            use_district = False
        elif role.type == "governor":
            role_name = "Governor"
            if role.jurisdiction == "ocd-jurisdiction/country:us/district:dc/government":
                role_name = "Mayor"
            org_type = "executive"
            use_district = False
        elif role.type in ("secretary of state", "chief election officer"):
            role_name = role.type.title()
            org_type = "executive"
            use_district = False
        elif role.type in ("upper", "lower", "legislature"):
            org_type = role.type
            use_district = True
        else:
            raise ValueError(f"unsupported role type: {role.type}")
        try:
            org = cached_lookup(
                Organization, classification=org_type, jurisdiction_id=role.jurisdiction
            )
            if use_district:
                post = org.posts.get(label=role.district)
            else:
                post = None
        except Organization.DoesNotExist:
            click.secho(f"{person} no such organization {role.jurisdiction} {org_type}", fg="red")
            raise CancelTransaction()
        except Post.DoesNotExist:
            # if this is a legacy district, be quiet
            lds = legacy_districts(jurisdiction_id=role.jurisdiction)
            if role.district not in lds[role.type]:
                click.secho(f"no such post {role}", fg="red")
                raise CancelTransaction()
            else:
                post = None

        if role.is_active():
            current_jurisdiction_id = role.jurisdiction

            current_role = {"org_classification": org_type, "district": None, "division_id": None}
            if use_district:
                state_metadata = metadata.lookup(jurisdiction_id=role.jurisdiction)
                district = state_metadata.lookup_district(
                    name=str(role.district), chamber=role.type
                )
                assert district
                current_role["division_id"] = district.division_id
                current_role["title"] = getattr(state_metadata, role.type).title
                # try to force district to an int for sorting, but allow strings for non-numeric districts
                try:
                    current_role["district"] = int(role.district)  # type: ignore
                except ValueError:
                    current_role["district"] = str(role.district)
            else:
                current_role["title"] = role_name
        elif not current_jurisdiction_id:
            current_jurisdiction_id = role.jurisdiction

        membership = {
            "organization": org,
            "post": post,
            "start_date": role.start_date,
            "end_date": role.end_date,
        }
        if not use_district:
            membership["role"] = role_name
        memberships.append(membership)

    # note that we don't manage committee memberships here
    updated |= update_subobjects(
        person,
        "memberships",
        memberships,
        read_manager=person.memberships.exclude(organization__classification="committee"),
    )

    # set computed fields (avoid extra save)
    if (
        person.primary_party != primary_party
        or person.current_role != current_role
        or person.current_jurisdiction_id != current_jurisdiction_id
    ):
        person.primary_party = primary_party
        person.current_role = current_role
        person.current_jurisdiction_id = current_jurisdiction_id
        person.save()

    return created, updated


def create_parties() -> None:
    from openstates.data.models import Organization

    for party in PartyName:
        org, created = Organization.objects.get_or_create(name=party.value, classification="party")
        if created:
            click.secho(f"created party: {party.value}", fg="green")


def create_municipalities(jurisdictions: list[DataDict]) -> None:
    from openstates.data.models import Jurisdiction, Organization

    for jurisdiction in jurisdictions:
        j, created = Jurisdiction.objects.get_or_create(
            id=jurisdiction["id"], name=jurisdiction["name"], classification="municipality"
        )
        if created:
            click.secho(f"created jurisdiction: {j.name}", fg="green")

        o, created = Organization.objects.get_or_create(
            jurisdiction=j, classification="government", name=f"{jurisdiction['name']} Government"
        )
        if created:
            click.secho(f"created organization: {o.name}", fg="green")
