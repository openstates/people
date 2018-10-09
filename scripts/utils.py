import re
import os

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
    return os.path.join(os.path.dirname(__file__), '../test/', abbr)


def get_jurisdiction_id(abbr):
    if abbr == 'dc':
        return 'ocd-jurisdiction/country:us/district:dc/government'
    elif abbr in ('vi', 'pr'):
        return f'ocd-jurisdiction/country:us/territory:{abbr}/government'
    else:
        return f'ocd-jurisdiction/country:us/state:{abbr}/government'
