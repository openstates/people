import re
import os
import datetime
import yaml
import yamlordereddictloader
from collections import defaultdict
from yaml.representer import Representer
# set up defaultdict representation
yaml.add_representer(defaultdict, Representer.represent_dict)

PHONE_RE = re.compile(r'''^
                      \D*(1?)\D*                                # prefix
                      (\d{3})\D*(\d{3})\D*(\d{4}).*?             # main 10 digits
                      (?:(?:ext|Ext|EXT)\.?\s*\s*(\d{1,4}))?    # extension
                      $''', re.VERBOSE)


def reformat_phone_number(phone):
    match = PHONE_RE.match(phone)
    if match:
        groups = match.groups()

        ext = groups[-1]
        if ext:
            ext = f' ext. {ext}'
        else:
            ext = ''

        if not groups[0]:
            groups = groups[1:-1]
        else:
            groups = groups[:-1]
        return '-'.join(groups) + ext
    else:
        return phone


def reformat_address(address):
    return re.sub(r'\s+', ' ', re.sub(r'\s*\n\s*', ';', address))


def get_data_dir(abbr):
    return os.path.join(os.path.dirname(__file__), '../data', abbr)


def get_jurisdiction_id(abbr):
    if abbr == 'dc':
        return 'ocd-jurisdiction/country:us/district:dc/government'
    elif abbr in ('vi', 'pr'):
        return f'ocd-jurisdiction/country:us/territory:{abbr}/government'
    else:
        return f'ocd-jurisdiction/country:us/state:{abbr}/government'


def load_yaml(file_obj):
    return yaml.load(file_obj, Loader=yamlordereddictloader.SafeLoader)


def dump_obj(obj, *, output_dir=None, filename=None):
    if output_dir:
        filename = os.path.join(output_dir, get_filename(obj))
    if not filename:
        raise ValueError('must provide output_dir or filename parameter')
    with open(filename, 'w') as f:
        yaml.dump(obj, f, default_flow_style=False, Dumper=yamlordereddictloader.SafeDumper)


def get_filename(obj):
    id = obj['id'].split('/')[1]
    name = obj['name']
    name = re.sub(r'\s+', '-', name)
    name = re.sub(r'[^a-zA-Z-]', '', name)
    return f'{name}-{id}.yml'


def role_is_active(role):
    now = datetime.datetime.utcnow().date().isoformat()
    return str(role.get('end_date')) is None or str(role.get('end_date')) > now
