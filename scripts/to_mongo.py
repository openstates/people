#!/usr/bin/env python

import datetime
import click
import pymongo
from utils import iter_objects, get_all_abbreviations, role_is_active


def dir_to_mongo(abbr):
    db = pymongo.MongoClient()['fiftystates']

    metadata = db.metadata.find({'_id': abbr})[0]
    latest_term = metadata['terms'][-1]['name']

    for person, filename in iter_objects(abbr, 'people'):

        legacy_ids = [oid['identifier'] for oid in person.get('other_identifiers', [])
                      if oid['scheme'] == 'legacy_openstates']

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
        created_at = updated_at = datetime.datetime.utcnow()
        old_roles = {}
        try:
            old_person = db.legislators.find({'_id': legacy_ids[0]})[0]
            created_at = old_person['created_at']
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
            'photo_url': person['image'],
            'state': abbr,
            'district': district,
            'chamber': chamber,
            'party': party,
            'email': email,
            'url': url,
            'created_at': created_at,
            'updated_at': updated_at,

            'first_name': '',
            'middle_name': '',
            'last_name': '',
            'suffixes': '',
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
        db.legislators.save(mongo_person)


@click.command()
@click.argument('abbreviations', nargs=-1)
@click.option('--purge/--no-purge', default=False,
              help="Purge all legislators from DB that aren't in YAML.")
@click.option('--safe/--no-safe', default=False,
              help="Operate in safe mode, no changes will be written to database.")
def to_database(abbreviations, purge, safe):
    """
    Sync YAML files to legacy MongoDB.
    """

    if not abbreviations:
        abbreviations = get_all_abbreviations()

    for abbr in abbreviations:
        click.secho('==== {} ===='.format(abbr), bold=True)
        dir_to_mongo(abbr)


if __name__ == '__main__':
    to_database()
