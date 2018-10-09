#!/usr/bin/env python
import os
import glob
import yaml
import django
import click
from utils import get_data_dir


def update_subobjects(person, fieldname, objects):
    """ returns True if there are any updates """
    manager = getattr(person, fieldname)
    current_count = manager.count()
    updated = False

    # if counts differ, we need to do an update for sure
    if current_count != len(objects):
        updated = True

    # check if all objects exist
    for obj in objects:
        if updated:
            break
        if manager.filter(**obj).count() != 1:
            updated = True

    # if there's been an update, wipe the old & insert the new
    if updated:
        if current_count:
            manager.all().delete()
        for obj in objects:
            manager.create(**obj)
        # save to bump updated_at timestamp
        person.save()

    return updated


def load_yaml(data):
    # import has to be here so that Django is set up
    from opencivicdata.core.models import Person, Organization

    created = False
    updated = False

    fields = dict(name=data['name'],
                  given_name=data.get('given_name', ''),
                  family_name=data.get('family_name', ''),
                  gender=data.get('gender', ''),
                  biography=data.get('biography', ''),
                  birth_date=data.get('birth_date', ''),
                  death_date=data.get('death_date', ''),
                  image=data.get('image', ''),
                  extras=data.get('extras', {}),
                  )

    try:
        person = Person.objects.get(pk=data['id'])
        for field, value in fields.items():
            if getattr(person, field) != value:
                setattr(person, field, value)
                updated = True
        if updated:
            person.save()
    except Person.DoesNotExist:
        person = Person.objects.create(id=data['id'], **fields)
        created = True

    updated |= update_subobjects(person, 'other_names', data.get('other_names', []))
    updated |= update_subobjects(person, 'links', data.get('links', []))
    updated |= update_subobjects(person, 'sources', data.get('sources', []))

    identifiers = []
    for scheme, value in data.get('ids', {}).items():
        identifiers.append({'scheme': scheme, 'identifier': value})
    for identifier in data.get('other_identifiers', []):
        identifiers.append(identifier)
    updated |= update_subobjects(person, 'identifiers', identifiers)

    contact_details = []
    for cd in data.get('contact_details', []):
        for type in ('address', 'email', 'voice', 'fax'):
            if cd.get(type):
                contact_details.append({'note': cd.get('note', ''),
                                        'type': type,
                                        'value': cd[type]})
    updated |= update_subobjects(person, 'contact_details', contact_details)

    memberships = []
    # for committee in data.get('committees', []):
    #     org = Organization.objects.get(classification='committee', name=committee['name'])
    #     memberships.append({'organization': org,
    #                         'start_date': party.get('start_date', ''),
    #                         'end_date': party.get('end_date', '')})
    for party in data.get('party', []):
        org = Organization.objects.get(classification='party', name=party['name'])
        memberships.append({'organization': org,
                            'start_date': party.get('start_date', ''),
                            'end_date': party.get('end_date', '')})
    for role in data.get('roles', []):
        if role['type'] in ('upper', 'lower', 'legislature'):
            org = Organization.objects.get(classification=role['type'],
                                           jurisdiction_id=role['jurisdiction'])
            post = org.posts.get(label=role['district'])
        else:
            raise ValueError('unsupported role type')
        memberships.append({'organization': org,
                            'post': post,
                            'start_date': role.get('start_date', ''),
                            'end_date': role.get('end_date', '')})
    updated |= update_subobjects(person, 'memberships', memberships)

    return created, updated


def load_directory(dirname):
    files = glob.glob(os.path.join(dirname, './*.yml'))
    for filename in files:
        with open(filename) as f:
            data = yaml.load(f)
            created, updated = load_yaml(data)
        if created:
            print('created legislator from', filename)
        elif updated:
            print('updated legislator from', filename)


@click.command()
@click.argument('abbr', default='*')
@click.option('-v', '--verbose', count=True)
@click.option('--summary/--no-summary', default=False)
def to_database(abbr, verbose, summary):
    directory = get_data_dir(abbr)
    load_directory(directory)


if __name__ == '__main__':
    # configure Django before model imports
    if os.environ.get("DJANGO_SETTINGS_MODULE") is None:
        os.environ['DJANGO_SETTINGS_MODULE'] = 'pupa.settings'
    django.setup()
    to_database()
