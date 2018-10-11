#!/usr/bin/env python
import os
import glob
import click
from utils import load_yaml, dump_obj, role_is_active


def retire_from_committees(person_id, end_date, committee_dir):
    num = 0

    for com_filename in glob.glob(os.path.join(committee_dir, '*.yml')):
        with open(com_filename) as f:
            committee = load_yaml(f)

        for role in committee['memberships']:
            if role.get('id') == person_id and role_is_active(role):
                role['end_date'] = end_date
                num += 1
                dump_obj(committee, filename=com_filename)
    return num


def retire_person(filename, end_date):
    with open(filename) as f:
        person = load_yaml(f)

    committee_dir = os.path.join(os.path.dirname(filename), '../organizations')
    num = retire_from_committees(person['id'], end_date, committee_dir)

    for role in person['roles']:
        if role_is_active(role):
            role['end_date'] = end_date
            num += 1

    if num == 0:
        click.secho('no active roles to retire', fg='red')
    elif num == 1:
        click.secho(f'retired person')
    else:
        click.secho(f'retired person from {num} roles')

    dump_obj(person, filename=filename)


def move_file(filename):
    os.renames(filename, filename.replace('/people/', '/retired/'))


@click.command()
@click.argument('end_date')
@click.argument('filename')
def retire(end_date, filename):
    retire_person(filename, end_date)
    move_file(filename)


if __name__ == '__main__':
    retire()
