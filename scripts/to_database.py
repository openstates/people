#!/usr/bin/env python
import os
import glob
import yaml
import django
from django import conf
from django.db import transaction
import click
from utils import get_data_dir, get_jurisdiction_id

class CancelTransaction(Exception):
    pass


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
    from opencivicdata.core.models import Person, Organization, Post

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
        try:
            org = Organization.objects.get(classification='party', name=party['name'])
        except Organization.DoesNotExist:
            click.secho(f"no such party {party['name']}", fg='red')
            raise
        memberships.append({'organization': org,
                            'start_date': party.get('start_date', ''),
                            'end_date': party.get('end_date', '')})
    for role in data.get('roles', []):
        if role['type'] in ('upper', 'lower', 'legislature'):
            try:
                org = Organization.objects.get(classification=role['type'],
                                               jurisdiction_id=role['jurisdiction'])
                post = org.posts.get(label=role['district'])
            except Organization.DoesNotExist:
                click.secho(f"no such organization {role}", fg='red')
                raise
            except Post.DoesNotExist:
                click.secho(f"no such post {role}", fg='red')
                raise
        else:
            raise ValueError('unsupported role type')
        memberships.append({'organization': org,
                            'post': post,
                            'start_date': role.get('start_date', ''),
                            'end_date': role.get('end_date', '')})

    updated |= update_subobjects(person, 'memberships', memberships)

    return created, updated


def load_directory(dirname, jurisdiction_id, purge):
    files = glob.glob(os.path.join(dirname, './*.yml'))
    ids = set()

    from opencivicdata.core.models import Person
    existing_ids = set(Person.objects.filter(
        memberships__organization__jurisdiction_id=jurisdiction_id
    ).values_list('id', flat=True))

    try:
        with transaction.atomic():
            for filename in files:
                with open(filename) as f:
                    data = yaml.load(f)
                    ids.add(data['id'])
                    created, updated = load_yaml(data)

                if created:
                    click.secho(f'created legislator from {filename}')
                elif updated:
                    click.secho(f'updated legislator from {filename}')

            missing_ids = existing_ids - ids
            if missing_ids and not purge:
                click.secho(f'{len(missing_ids)} went missing, run with --purge to remove',
                            fg='red')
                for id in missing_ids:
                    click.secho(f'  {id}')
                raise CancelTransaction()
            elif missing_ids and purge:
                click.secho(f'{len(missing_ids)} people purged', fg='yellow')
                Person.objects.filter(id__in=missing_ids).delete()

            # TODO: check new_ids?
            # new_ids = ids - existing_ids

    except CancelTransaction:
        pass




def init_django():
    conf.settings.configure(
        conf.global_settings,
        SECRET_KEY='not-important',
        DEBUG=False,
        INSTALLED_APPS=(
             'django.contrib.contenttypes',
             'opencivicdata.core.apps.BaseConfig',
             'opencivicdata.legislative.apps.BaseConfig'
        ),
        DATABASES={
            'default': {
                'ENGINE': 'django.contrib.gis.db.backends.postgis',
                'NAME': os.environ['OCD_DATABASE_NAME'],
                'USER': os.environ['OCD_DATABASE_USER'],
                'PASSWORD': os.environ['OCD_DATABASE_PASSWORD'],
                'HOST': 'localhost',
            }
        },
        MIDDLEWARE_CLASSES=(),
    )
    django.setup()


@click.command()
@click.argument('abbr', default='*')
@click.option('-v', '--verbose', count=True)
@click.option('--summary/--no-summary', default=False)
@click.option('--purge/--no-purge', default=False)
def to_database(abbr, verbose, summary, purge):
    init_django()
    directory = get_data_dir(abbr)
    jurisdiction_id = get_jurisdiction_id(abbr)
    load_directory(directory, jurisdiction_id, purge)


if __name__ == '__main__':
    to_database()
