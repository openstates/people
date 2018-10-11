#!/usr/bin/env python
import os
import glob
import click
from utils import load_yaml, dump_obj, role_is_active


def retire_from_committee(committee, person_id, end_date):
    num = 0
    for role in committee['memberships']:
        if role.get('id') == person_id and role_is_active(role):
            role['end_date'] = end_date
            num += 1
    return committee, num


def retire_person(person, end_date):
    num = 0
    for role in person['roles']:
        if role_is_active(role):
            role['end_date'] = end_date
            num += 1
    return person, num


def move_file(filename):
    new_filename = filename.replace('/people/', '/retired/')
    click.secho(f'moved from {filename} to {new_filename}')
    os.renames(filename, new_filename)


@click.command()
@click.argument('end_date')
@click.argument('filename')
def retire(end_date, filename):
    # end the person's active roles & re-save
    with open(filename) as f:
        person = load_yaml(f)
    person, num = retire_person(person, end_date)
    dump_obj(person, filename=filename)

    # same for their committees
    committee_glob = os.path.join(os.path.dirname(filename), '../organizations/*.yml')
    for com_filename in glob.glob(committee_glob):
        with open(com_filename) as f:
            committee = load_yaml(f)
        committee, num_roles = retire_from_committee(committee, person['id'], end_date)
        dump_obj(committee, filename=com_filename)
        num += num_roles

    if num == 0:
        click.secho('no active roles to retire', fg='red')
    elif num == 1:
        click.secho(f'retired person')
    else:
        click.secho(f'retired person from {num} roles')

    move_file(filename)


if __name__ == '__main__':
    retire()
