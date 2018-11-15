#!/usr/bin/env python

import os
import click
from utils import ocd_uuid, get_jurisdiction_id, get_data_dir, dump_obj


def create_person(fname, lname, name, state, district, party, rtype, url, image,
                  start_date):
    person = {
        'id': ocd_uuid('person'),
        'name': name or f'{fname} {lname}',
        'given_name': fname,
        'family_name': lname,
        'image': image,
        'party': [{'name': party}],
        'roles': [
            {'type': rtype,
             'district': district,
             'jurisdiction': get_jurisdiction_id(state),
             'start_date': start_date,
             }
        ],
        'links': [{'url': url}],
        'sources': [{'url': url}],
    }

    output_dir = get_data_dir(state)
    dump_obj(person, output_dir=os.path.join(output_dir, 'people'))


@click.command()
@click.option('--fname', prompt='First Name')
@click.option('--lname', prompt='Last Name')
@click.option('--name')
@click.option('--state', prompt='State')
@click.option('--district', prompt='District')
@click.option('--party', prompt='Party')
@click.option('--rtype', prompt='Role Type (upper|lower)')
@click.option('--url', prompt='URL')
@click.option('--image', prompt='Image URL')
@click.option('--start-date', prompt='Start Date')
def new_person(fname, lname, name, state, district, party, rtype, url, image, start_date):
    """
    Create a new person record.
    """
    create_person(fname=fname, lname=lname, name=name,
                  state=state, district=district, party=party,
                  rtype=rtype, url=url, image=image,
                  start_date=start_date)

if __name__ == '__main__':
    new_person()
