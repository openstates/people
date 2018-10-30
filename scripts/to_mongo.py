#!/usr/bin/env python
import os
import sys
import datetime
import click
import pymongo
import name_tools
from utils import iter_objects, get_all_abbreviations, role_is_active, dump_obj


def get_next_id(db, abbr):
    cur_max = max([max(x['_all_ids']) for x in db.legislators.find({'state': abbr})])
    new_id = int(cur_max[3:]) + 1

    return f'{abbr.upper()}L{new_id:06d}'


def dir_to_mongo(abbr, create, clear_old_roles, verbose):
    db = pymongo.MongoClient(os.environ.get('BILLY_MONGO_HOST', 'localhost'))['fiftystates']

    metadata = db.metadata.find({'_id': abbr})[0]
    latest_term = metadata['terms'][-1]['name']

    active_ids = []

    for person, filename in iter_objects(abbr, 'people'):

        legacy_ids = [oid['identifier'] for oid in person.get('other_identifiers', [])
                      if oid['scheme'] == 'legacy_openstates']
        if not legacy_ids:
            if create:
                # get next ID
                new_id = get_next_id(db, abbr)
                legacy_ids = [new_id]
                if 'other_identifiers' not in person:
                    person['other_identifiers'] = []
                person['other_identifiers'].append({'scheme': 'legacy_openstates',
                                                    'identifier': new_id})
                dump_obj(person, filename=filename)
            else:
                click.secho(f'{filename} does not have legacy ID, run with --create', fg='red')
                sys.exit(1)

        active_ids.append(legacy_ids[0])

        # handle name
        prefix, first_name, last_name, suffixes = name_tools.split(person['name'])

        # get chamber, district, party
        for role in person['roles']:
            if role_is_active(role):
                chamber = role['type']
                district = role['district']
                break
        for role in person['party']:
            if role_is_active(role):
                party = role['name']

        url = person['links'][0]['url']
        email = ''

        offices = []
        for cd in person.get('contact_details', []):
            office = {'fax': cd.get('fax'),
                      'phone': cd.get('voice'),
                      'address': cd.get('address'),
                      'email': cd.get('email'),
                      'name': cd['note'],
                      'type': 'capitol' if 'capitol' in cd['note'].lower() else 'district'
                      }
            offices.append(office)
            if office['email'] and not email:
                email = office['email']

        # NE & DC
        if chamber == 'legislature':
            chamber = 'upper'

        # get some old data to keep around
        created_at = datetime.datetime.utcnow()
        old_roles = {}
        old_person = None
        try:
            old_person = db.legislators.find({'_id': legacy_ids[0]})[0]
            created_at = old_person['created_at']
            if not clear_old_roles:
                old_roles = old_person.get('old_roles', {})
        except IndexError:
            pass

        mongo_person = {
            '_id': legacy_ids[0],
            'leg_id': legacy_ids[0],
            '_all_ids': legacy_ids,
            '_type': 'person',
            'active': True,
            'full_name': person['name'],
            '_scraped_name': person['name'],
            'photo_url': person.get('image'),
            'state': abbr,
            'district': district,
            'chamber': chamber,
            'party': party,
            'email': email,
            'url': url,
            'offices': offices,
            'created_at': created_at,

            'first_name': first_name,
            'middle_name': '',
            'last_name': last_name,
            'suffixes': suffixes,
            'sources': person['sources'],

            'old_roles': old_roles,
            'roles': [
                {'term': latest_term, 'district': district, 'chamber': chamber, 'state': abbr,
                 'party': party, 'type': 'member', 'start_date': None, 'end_date': None},
            ],
        }
        # TODO: committee info
        # { "term" : "2017-2018", "committee_id" : "NCC000233", "chamber" : "lower",
        # "state" : "nc", "subcommittee" : null, "committee" : "State and Local Government II",
        # "position" : "member", "type" : "committee member" },

        # compare
        if old_person:
            old_person.pop('updated_at', None)
        if old_person == mongo_person:
            if verbose:
                click.secho(f'no updates to {mongo_person["_id"]}')
        else:
            # print(mongo_person, old_person)
            # raise Exception()
            click.secho(f'updating {mongo_person["_id"]}', fg='green')
            mongo_person['updated_at'] = datetime.datetime.utcnow()
            try:
                db.legislators.save(mongo_person)
            except Exception as e:
                print(e)
                continue

    to_retire = db.legislators.find({'_id': {'$nin': active_ids}, 'state': abbr})
    click.secho(f'going to try to retire {to_retire.count()}')
    for leg in to_retire:
        retire_person(db, leg)


def retire_person(db, leg):
    if leg['active'] or leg['roles']:
        leg['active'] = False
        leg['roles'] = []
        leg['updated_at'] = datetime.datetime.utcnow()
        db.legislators.save(leg)
        click.secho(f'retired {leg["_id"]}', fg='blue')


@click.command()
@click.argument('abbreviations', nargs=-1)
@click.option('--create/--no-create', default=False)
@click.option('--clear-old-roles/--no-clear-old-roles', default=False)
@click.option('-v', '--verbose', count=True)
def to_database(abbreviations, create, verbose, clear_old_roles):
    """
    Sync YAML files to legacy MongoDB.
    """

    if not abbreviations:
        abbreviations = get_all_abbreviations()

    for abbr in abbreviations:
        click.secho('==== {} ===='.format(abbr), bold=True)
        dir_to_mongo(abbr, create, clear_old_roles, verbose)


if __name__ == '__main__':
    to_database()
