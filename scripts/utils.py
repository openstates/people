import re
import os
import glob
import uuid
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


def ocd_uuid(type):
    return 'ocd-{}/{}'.format(type, uuid.uuid4())


def get_data_dir(abbr):
    return os.path.join(os.path.dirname(__file__), '../data', abbr)


def get_all_abbreviations():
    return sorted(os.listdir(os.path.join(os.path.dirname(__file__), '../data')))


def get_jurisdiction_id(abbr):
    if abbr == 'dc':
        return 'ocd-jurisdiction/country:us/district:dc/government'
    elif abbr in ('vi', 'pr'):
        return f'ocd-jurisdiction/country:us/territory:{abbr}/government'
    else:
        return f'ocd-jurisdiction/country:us/state:{abbr}/government'


def load_yaml(file_obj):
    return yaml.load(file_obj, Loader=yamlordereddictloader.SafeLoader)


def iter_objects(abbr, objtype):
    filenames = glob.glob(os.path.join(get_data_dir(abbr), objtype, '*.yml'))
    for filename in filenames:
        with open(filename) as f:
            yield load_yaml(f), filename


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


def get_districts(settings):
    expected = {}
    for key in ('upper', 'lower', 'legislature'):
        seats = settings.get(key + '_seats')
        if not seats:
            continue
        elif isinstance(seats, int):
            # one seat per district by default
            expected[key] = {str(s): 1 for s in range(1, seats+1)}
        elif isinstance(seats, list):
            expected[key] = {str(s): 1 for s in seats}
        elif isinstance(seats, dict):
            expected[key] = seats
        else:   # pragma: no cover
            raise ValueError(seats)
    return expected
