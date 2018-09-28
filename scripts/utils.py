import re
import os


def reformat_phone_number(phone):
    match = re.match(r'^.*(1?).*(\d{3}).*(\d{3}).*(\d{4})$', phone)
    if match:
        groups = match.groups()
        if groups[0] == '':
            groups = groups[1:]
        return '-'.join(groups)
    else:
        return phone


def get_data_dir(state):
    return os.path.join(os.path.dirname(__file__), '../test/', state)
