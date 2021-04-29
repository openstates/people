#!/usr/bin/env python
import os
import sys
import glob
from functools import lru_cache
from django.db import transaction
import click
from openstates import metadata
from openstates.utils.django import init_django
from ..utils import (
    get_data_dir,
    get_all_abbreviations,
    load_yaml,
    legacy_districts,
    role_is_active,
    load_municipalities,
    MAJOR_PARTIES,
)


class CancelTransaction(Exception):
    pass


@lru_cache(128)
def cached_lookup(ModelCls, **kwargs):
    return ModelCls.objects.get(**kwargs)


def update_subobjects(person, fieldname, objects, read_manager=None):
    """ returns True if there are any updates """
    # we need the default manager for this field in case we need to do updates
    manager = getattr(person, fieldname)

    # if a read_manager is passed, we'll use that for all read operations
    # this is used for Person.memberships to ensure we don't wipe out committee memberships
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


def get_update_or_create(ModelCls, data, lookup_keys):
    updated = created = False
    kwargs = {k: data[k] for k in lookup_keys}
    try:
        obj = ModelCls.objects.get(**kwargs)
        for field, value in data.items():
            if getattr(obj, field) != value:
                setattr(obj, field, value)
                updated = True
        if updated:
            obj.save()
    except ModelCls.DoesNotExist:
        obj = ModelCls.objects.create(**data)
        created = True
    return obj, created, updated


def load_person(data):
    # import has to be here so that Django is set up
    from openstates.data.models import Person, Organization, Post

    fields = dict(
        id=data["id"],
        name=data["name"],
        given_name=data.get("given_name", ""),
        family_name=data.get("family_name", ""),
        gender=data.get("gender", ""),
        email=data.get("email", ""),
        biography=data.get("biography", ""),
        birth_date=data.get("birth_date", ""),
        death_date=data.get("death_date", ""),
        image=data.get("image", ""),
        extras=data.get("extras", {}),
    )
    person, created, updated = get_update_or_create(Person, fields, ["id"])

    updated |= update_subobjects(person, "other_names", data.get("other_names", []))
    updated |= update_subobjects(person, "links", data.get("links", []))
    updated |= update_subobjects(person, "sources", data.get("sources", []))

    identifiers = []
    for scheme, value in data.get("ids", {}).items():
        identifiers.append({"scheme": scheme, "identifier": value})
    for identifier in data.get("other_identifiers", []):
        identifiers.append(identifier)
    updated |= update_subobjects(person, "identifiers", identifiers)

    contact_details = []
    for cd in data.get("contact_details", []):
        for type in ("address", "voice", "fax"):
            if cd.get(type):
                contact_details.append(
                    {"note": cd.get("note", ""), "type": type, "value": cd[type]}
                )
    updated |= update_subobjects(person, "contact_details", contact_details)

    memberships = []
    primary_party = ""
    current_jurisdiction_id = None
    current_role = None
    for party in data.get("party", []):
        party_name = party["name"]
        try:
            org = cached_lookup(Organization, classification="party", name=party["name"])
        except Organization.DoesNotExist:
            click.secho(f"no such party {party['name']}", fg="red")
            raise CancelTransaction()
        memberships.append(
            {
                "organization": org,
                "start_date": party.get("start_date", ""),
                "end_date": party.get("end_date", ""),
            }
        )
        if role_is_active(party):
            if primary_party in MAJOR_PARTIES and party_name in MAJOR_PARTIES:
                raise ValueError(f"two primary parties for ({data['name']} {data['id']})")
            elif primary_party in MAJOR_PARTIES:
                # already set correct primary party, so do nothing
                pass
            else:
                primary_party = party_name
    for role in data.get("roles", []):
        if role["type"] in ("mayor",):
            role_name = "Mayor"
            org_type = "government"
            use_district = False
        elif role["type"] == "governor":
            role_name = "Governor"
            if role["jurisdiction"] == "ocd-jurisdiction/country:us/district:dc/government":
                role_name = "Mayor"
            org_type = "executive"
            use_district = False
        elif role["type"] in ("secretary of state", "chief election officer"):
            role_name = role["type"].title()
            org_type = "executive"
            use_district = False
        elif role["type"] in ("upper", "lower", "legislature"):
            org_type = role["type"]
            use_district = True
        else:
            raise ValueError(f"unsupported role type: {role['type']}")
        try:
            org = cached_lookup(
                Organization, classification=org_type, jurisdiction_id=role["jurisdiction"]
            )
            if use_district:
                post = org.posts.get(label=role["district"])
            else:
                post = None
        except Organization.DoesNotExist:
            click.secho(
                f"{person} no such organization {role['jurisdiction']} {org_type}", fg="red"
            )
            raise CancelTransaction()
        except Post.DoesNotExist:
            # if this is a legacy district, be quiet
            lds = legacy_districts(jurisdiction_id=role["jurisdiction"])
            if role["district"] not in lds[role["type"]]:
                click.secho(f"no such post {role}", fg="red")
                raise CancelTransaction()
            else:
                post = None

        if role_is_active(role):
            current_jurisdiction_id = role["jurisdiction"]

            current_role = {"org_classification": org_type, "district": None, "division_id": None}
            if use_district:
                state_metadata = metadata.lookup(jurisdiction_id=role["jurisdiction"])
                district = state_metadata.lookup_district(
                    name=str(role["district"]), chamber=role["type"]
                )
                assert district
                current_role["division_id"] = district.division_id
                current_role["title"] = getattr(state_metadata, role["type"]).title
                # try to force district to an int for sorting, but allow strings for non-numeric districts
                try:
                    current_role["district"] = int(role["district"])
                except ValueError:
                    current_role["district"] = str(role["district"])
            else:
                current_role["title"] = role_name
        elif not current_jurisdiction_id:
            current_jurisdiction_id = role["jurisdiction"]

        membership = {
            "organization": org,
            "post": post,
            "start_date": role.get("start_date", ""),
            "end_date": role.get("end_date", ""),
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


def _echo_org_status(org, created, updated):
    if created:
        click.secho(f"{org} created", fg="green")
    elif updated:
        click.secho(f"{org} updated", fg="yellow")


def load_directory(files, purge):
    from openstates.data.models import Person, BillSponsorship, PersonVote

    ids = set()
    merged = {}
    created_count = 0
    updated_count = 0

    all_data = []
    all_jurisdictions = []
    for filename in files:
        with open(filename) as f:
            data = load_yaml(f)
            all_data.append((data, filename))
            if data.get("roles"):
                all_jurisdictions.append(data["roles"][0]["jurisdiction"])

    existing_ids = set(
        Person.objects.filter(
            memberships__organization__jurisdiction_id__in=all_jurisdictions
        ).values_list("id", flat=True)
    )

    for data, filename in all_data:
        ids.add(data["id"])
        created, updated = load_person(data)

        if created:
            click.secho(f"created person from {filename}", fg="cyan", bold=True)
            created_count += 1
        elif updated:
            click.secho(f"updated person from {filename}", fg="cyan")
            updated_count += 1

    missing_ids = existing_ids - ids

    # check if missing ids are in need of a merge
    for missing_id in missing_ids:
        try:
            found = Person.objects.get(
                identifiers__identifier=missing_id, identifiers__scheme="openstates"
            )
            merged[missing_id] = found.id
        except Person.DoesNotExist:
            pass

    if merged:
        click.secho(f"{len(merged)} removed via merge", fg="yellow")
        for old, new in merged.items():
            click.secho(f"   {old} => {new}", fg="yellow")
            BillSponsorship.objects.filter(person_id=old).update(person_id=new)
            PersonVote.objects.filter(voter_id=old).update(voter_id=new)
            Person.objects.filter(id=old).delete()
            missing_ids.remove(old)

    # ids that are still missing would need to be purged
    if missing_ids and not purge:
        click.secho(f"{len(missing_ids)} went missing, run with --purge to remove", fg="red")
        for id in missing_ids:
            mobj = Person.objects.get(pk=id)
            click.secho(f"  {id}: {mobj}")
        raise CancelTransaction()
    elif missing_ids and purge:
        click.secho(f"{len(missing_ids)} purged", fg="yellow")
        Person.objects.filter(id__in=missing_ids).delete()

    click.secho(
        f"processed {len(ids)} person files, {created_count} created, " f"{updated_count} updated",
        fg="green",
    )


def create_parties():
    from openstates.data.models import Organization

    settings_file = os.path.join(os.path.dirname(__file__), "../settings.yml")
    with open(settings_file) as f:
        settings = load_yaml(f)
    parties = settings["parties"]
    for party in parties:
        org, created = Organization.objects.get_or_create(name=party, classification="party")
        if created:
            click.secho(f"created party: {party}", fg="green")


def create_municipalities(jurisdictions):
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


@click.command()
@click.argument("abbreviations", nargs=-1)
@click.option(
    "--purge/--no-purge", default=False, help="Purge all legislators from DB that aren't in YAML."
)
@click.option(
    "--safe/--no-safe",
    default=False,
    help="Operate in safe mode, no changes will be written to database.",
)
def to_database(abbreviations, purge, safe):
    """
    Sync YAML files to DB.
    """
    init_django()

    create_parties()

    if not abbreviations:
        abbreviations = get_all_abbreviations()

    for abbr in abbreviations:
        click.secho("==== {} ====".format(abbr), bold=True)
        directory = get_data_dir(abbr)
        municipalities = load_municipalities(abbr)

        with transaction.atomic():
            create_municipalities(municipalities)

        person_files = (
            glob.glob(os.path.join(directory, "legislature/*.yml"))
            + glob.glob(os.path.join(directory, "executive/*.yml"))
            + glob.glob(os.path.join(directory, "municipalities/*.yml"))
            + glob.glob(os.path.join(directory, "retired/*.yml"))
        )

        if safe:
            click.secho("running in safe mode, no changes will be made", fg="magenta")

        try:
            with transaction.atomic():
                load_directory(person_files, purge=purge)
                if safe:
                    click.secho("ran in safe mode, no changes were made", fg="magenta")
                    raise CancelTransaction()
        except CancelTransaction:
            sys.exit(1)


if __name__ == "__main__":
    to_database()
