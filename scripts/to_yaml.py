#!/usr/bin/env python
import glob
import json
import os
import uuid
import click
from collections import defaultdict, OrderedDict
from utils import (reformat_phone_number, reformat_address, get_data_dir, get_jurisdiction_id,
                   dump_obj)


def process_link(link):
    if not link['note']:
        del link['note']
    return link


def process_dir(input_dir, output_dir, jurisdiction_id):
    person_memberships = defaultdict(list)
    # map both names & ids to people objects
    people_lookup = {}
    committees_by_id = {}

    # build list of committees
    for filename in glob.glob(os.path.join(input_dir, 'organization_*.json')):
        with open(filename) as f:
            org = json.load(f)

        if org['classification'] == 'committee':
            committees_by_id[org['_id']] = process_org(org, jurisdiction_id)

    # collect memberships
    for filename in glob.glob(os.path.join(input_dir, 'membership_*.json')):
        with open(filename) as f:
            membership = json.load(f)

        if membership['organization_id'] in committees_by_id:
            committees_by_id[membership['organization_id']]['memberships'].append(membership)
        else:
            if membership['person_id'].startswith('~'):
                raise ValueError(membership)
            person_memberships[membership['person_id']].append(membership)

    # process people & store people by ID for committees
    for filename in glob.glob(os.path.join(input_dir, 'person_*.json')):
        with open(filename) as f:
            person = json.load(f)

        scrape_id = person['_id']
        person['memberships'] = person_memberships[scrape_id]
        person = process_person(person, jurisdiction_id)
        people_lookup[scrape_id] = person
        people_lookup[person['name']] = person

        dump_obj(person, os.path.join(output_dir, 'people'))

    # resolve committee parents and members and write them out
    for org in committees_by_id.values():
        if org['parent'].startswith('~'):
            org['parent'] = json.loads(org['parent'][1:])['classification']

        org['memberships'] = [process_committee_membership(m, people_lookup)
                              for m in org['memberships']]

        dump_obj(org, os.path.join(output_dir, 'organizations'))


def process_committee_membership(membership, people_lookup):
    result = OrderedDict()
    if membership['person_id'].startswith('~'):
        try:
            result['id'] = people_lookup[membership['person_name']]['id']
        except KeyError:
            # there are many unresolved people for all sorts of reasons,
            # we'll see them in the lint
            pass
    else:
        result['id'] = people_lookup[membership['person_id']]['id']

    result['name'] = membership['person_name']
    if membership['role'] != 'member':
        result['role'] = membership['role']
    if membership['start_date']:
        result['start_date'] = membership['start_date']
    if membership['end_date']:
        result['end_date'] = membership['end_date']
    return result


def process_person(person, jurisdiction_id):
    optional_keys = (
        'image',
        'gender',
        'biography',
        'given_name',
        'family_name',
        'birth_date',
        'death_date',
        'national_identity',
        'summary',
        # maybe post-process these?
        'other_names',
    )

    result = OrderedDict(
        id=str(uuid.uuid4()),        # let's use uuid4 for these, override pupa's
        name=person['name'],
        party=[],
        roles=[],
        links=[process_link(link) for link in person['links']],
        contact_details=[],
        # maybe post-process these?
        sources=[process_link(link) for link in person['sources']],
    )

    contact_details = defaultdict(lambda: defaultdict(list))
    for detail in person['contact_details']:
        value = detail['value']
        if detail['type'] in ('voice', 'fax'):
            value = reformat_phone_number(value)
        elif detail['type'] == 'address':
            value = reformat_address(value)
        contact_details[detail['note']][detail['type']] = value

    result['contact_details'] = [{'note': key, **val} for key, val in contact_details.items()]

    # memberships!
    for membership in person['memberships']:
        organization_id = membership['organization_id']
        if not organization_id.startswith('~'):
            raise ValueError(organization_id)
        org = json.loads(organization_id[1:])
        if org['classification'] in ('upper', 'lower'):
            post = json.loads(membership['post_id'][1:])['label']
            result['roles'] = [
                {'type': org['classification'], 'district': post,
                 'jurisdiction': jurisdiction_id}
            ]
        elif org['classification'] == 'party':
            result['party'] = [
                {'name': org['name']}
            ]

    for key in optional_keys:
        if person.get(key):
            result[key] = person[key]

    # promote some extras where appropriate
    extras = person.get('extras', {}).copy()
    for key in person.get('extras', {}).keys():
        if key in optional_keys:
            result[key] = extras.pop(key)
    if extras:
        result['extras'] = extras

    if person.get('identifiers'):
        result['other_identifiers'] = person['identifiers']

    return result


def process_org(org, jurisdiction_id):
    return OrderedDict(
        id=str(uuid.uuid4()),        # let's use uuid4 for these, override pupa's
        name=org['name'],
        jurisdiction=jurisdiction_id,
        parent=org['parent_id'],
        classification=org['classification'],
        links=[process_link(link) for link in org['links']],
        sources=[process_link(link) for link in org['sources']],
        memberships=[],
    )


@click.command()
@click.argument('input_dir')
@click.option('--reset/--no-reset', default=False)
def to_yaml(input_dir, reset):
    # TODO: remove reset option once we're in prod

    # abbr is last piece of directory name
    abbr = None
    for piece in input_dir.split('/')[::-1]:
        if piece:
            abbr = piece
            break

    output_dir = get_data_dir(abbr)
    jurisdiction_id = get_jurisdiction_id(abbr)

    for dir in ('people', 'organizations'):
        try:
            os.makedirs(os.path.join(output_dir, dir))
        except FileExistsError:
            if reset:
                for file in glob.glob(os.path.join(output_dir, dir, '*.yml')):
                    os.remove(file)
    process_dir(input_dir, output_dir, jurisdiction_id)


if __name__ == '__main__':
    to_yaml()
