#!/usr/bin/env python

import os
import glob
import yaml
import click
from utils import get_filename, get_data_dir, load_yaml, dump_obj


class ListDifference:
    def __init__(self, key_name, list_item, which_list):
        self.key_name = key_name
        self.list_item = list_item
        self.which_list = which_list

    def __eq__(self, other):
        return (self.key_name == other.key_name and
                self.list_item == other.list_item and
                self.which_list == other.which_list)

    def __str__(self):
        return f'{self.key_name}: {self.list_item} only in {self.which_list}'


class ItemDifference:
    def __init__(self, key_name, value_one, value_two):
        self.key_name = key_name
        self.value_one = value_one
        self.value_two = value_two

    def __eq__(self, other):
        return (self.key_name == other.key_name and
                self.value_one == other.value_one and
                self.value_two == other.value_two)

    def __str__(self):
        return f'{self.key_name}: {self.value_one} != {self.value_two}'


class MergeConflict(Exception):
    def __init__(self, difference):
        self.difference = difference

    def __str__(self):
        return str(self.difference)


def compare_objects(obj1, obj2, prefix='', ignore=None):
    combined_keys = set(obj1) | set(obj2)
    differences = []
    for key in combined_keys:
        if ignore and key in ignore:
            continue
        key_name = '.'.join((prefix, key)) if prefix else key
        val1 = obj1.get(key)
        val2 = obj2.get(key)
        if isinstance(val1, list) or isinstance(val2, list):
            # we can compare this way since order doesn't matter
            if val1 is None:
                val1 = []
            if val2 is None:
                val2 = []
            for item in val1:
                if item not in val2:
                    differences.append(ListDifference(key_name, item, 'first'))
            for item in val2:
                if item not in val1:
                    differences.append(ListDifference(key_name, item, 'second'))
        elif isinstance(val1, dict) or isinstance(val2, dict):
            differences.extend(compare_objects(val1 or {}, val2 or {}, prefix=key_name))
        elif val1 != val2:
            differences.append(ItemDifference(key_name, val1, val2))
    return differences


def calculate_similarity(existing, new):
    """
        if everything is equal except for the id: 1
        if names differ, maximum match is 0.8
        for each item that differs, we decrease score by 0.1
    """
    differences = compare_objects(
        existing, new,
        ignore=['id', 'other_identifiers', 'given_name', 'family_name']
    )

    # if nothing differs or only id differs
    if len(differences) == 0 or (len(differences) == 1 and differences[0].key_name == 'id'):
        return 1

    if existing['name'] != new['name']:
        score = 0.9     # will have another 0.1 deducted later
    else:
        score = 1

    score -= 0.1*len(differences)

    if score < 0:
        score = 0

    return score


def directory_merge(abbr, existing_people, new_people, remove_identical, copy_new):
    perfect_matched = set()
    matches = []
    id_to_new_filename = {}

    for new in new_people:
        best_similarity = 0
        best_match = None

        id_to_new_filename[new['id']] = get_filename(new)

        for existing in existing_people:
            similarity = calculate_similarity(existing, new)
            if similarity > 0.999:
                perfect_matched.add(new['id'])
                continue

            if similarity > best_similarity:
                best_similarity = similarity
                best_match = existing

        matches.append((best_similarity, new, best_match))

    click.secho(f'{len(perfect_matched)} were perfect matches', fg='green')

    if remove_identical:
        for id in perfect_matched:
            fname = id_to_new_filename[id]
            fname = f'incoming/{abbr}/people/{fname}'.format(fname)
            click.secho('removing ' + fname, fg='red')
            os.remove(fname)

    unmatched = set(p['id'] for p in new_people) - perfect_matched

    for sim, new, old in sorted(matches, reverse=True, key=lambda x: x[0]):
        if sim < 0.001:
            break
        unmatched.remove(new['id'])
        click.secho(' {:.2f} incoming/{}/people/{} data/{}/people/{}'.format(
            sim, abbr, get_filename(new), abbr, get_filename(old)), fg='yellow')

    click.secho(f'{len(unmatched)} were unmatched')
    for id in unmatched:
        fname = id_to_new_filename[id]
        oldfname = f'incoming/{abbr}/people/{fname}'.format(fname)
        if copy_new:
            newfname = f'data/{abbr}/people/{fname}'.format(fname)
            click.secho(f'moving {oldfname} to {newfname}', fg='yellow')
            os.rename(oldfname, newfname)


def merge_people(old, new, keep_on_conflict=None, keep_both_ids=False):
    differences = compare_objects(old, new)
    for difference in differences:

        if difference.key_name == 'id':
            if keep_both_ids:
                if 'other_identifiers' not in old:
                    old['other_identifiers'] = []
                old['other_identifiers'].append({'scheme': 'openstates',
                                                 'identifier': new['id']})
            continue

        if isinstance(difference, ItemDifference):
            if difference.value_one is None:
                old[difference.key_name] = difference.value_two
            elif difference.value_two is None:
                pass
            elif keep_on_conflict == 'old':
                pass
            elif keep_on_conflict == 'new':
                old[difference.key_name] = difference.value_two
            else:
                raise MergeConflict(difference)

        if isinstance(difference, ListDifference):
            # only need to handle case where item is only in second list
            if difference.which_list == 'second':
                old[difference.key_name].append(difference.list_item)
    return old


@click.command()
@click.option('--incoming', default=None,
              help='Operate in incoming mode, argument should be state abbr to scan.')
@click.option('--remove-identical/--no-remove-identical',
              help='In incoming mode, remove identical files.')
@click.option('--copy-new/--no-copy-new', default=None,
              help='In incoming mode, copy brand new files over.')
@click.option('--old', default=None,
              help='Operate in merge mode, this is the older of two files & will be kept.')
@click.option('--new', default=None,
              help='In merge mode, this is the newer file that will be removed after merge.')
@click.option('--keep', default=None,
              help='''When operating in merge mode, select which data to keep.
Values:
old
    Keep data in old file if there's conflict.
new
    Keep data in new file if there's conflict.

When omitted, conflicts will raise error.''')
def entrypoint(incoming, old, new, keep, remove_identical, copy_new):
    """
        Script to assist with merging legislator files.

        Can be used in two modes: incoming or file merge.

        Incoming mode analyzes incoming/ directory files (generated with to_yaml.py)
        and discovers identical & similar files to assist with merging.

        File merge mode merges two legislator files.
    """
    if incoming:
        abbr = incoming
        existing_people = []
        for filename in (glob.glob(os.path.join(get_data_dir(abbr), 'people/*.yml')) +
                         glob.glob(os.path.join(get_data_dir(abbr), 'retired/*.yml'))):
            with open(filename) as f:
                existing_people.append(yaml.load(f))

        new_people = []
        incoming_dir = get_data_dir(abbr).replace('data', 'incoming')
        for filename in glob.glob(os.path.join(incoming_dir, 'people/*.yml')):
            with open(filename) as f:
                new_people.append(yaml.load(f))

        click.secho(
            f'analyzing {len(existing_people)} existing people and {len(new_people)} incoming'
        )

        directory_merge(abbr, existing_people, new_people, remove_identical, copy_new)

    if old and new:
        with open(old) as f:
            old_obj = load_yaml(f)
        with open(new) as f:
            new_obj = load_yaml(f)
        if keep not in ('old', 'new'):
            raise ValueError('--keep parameter must be old or new')
        keep_both_ids = True
        if 'incoming' in new_obj:
            keep_both_ids = False
        merged = merge_people(old_obj, new_obj, keep_on_conflict=keep,
                              keep_both_ids=keep_both_ids)
        dump_obj(merged, filename=old)
        os.remove(new)
        click.secho(f'merged files into {old}\ndeleted {new}\ncheck git diff before committing')


if __name__ == '__main__':
    entrypoint()
