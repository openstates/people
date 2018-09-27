import re


def reformat_phone_number(phone):
    match = re.match(r'^.*(1?).*(\d{3}).*(\d{3}).*(\d{4})$', phone)
    if match:
        groups = match.groups()
        if groups[0] == '':
            groups = groups[1:]
        return '-'.join(groups)
    else:
        return phone
