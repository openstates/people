import re
import os
import glob
import uuid
import datetime
import yaml
import yamlordereddictloader
from collections import defaultdict
from yaml.representer import Representer
import openstates_metadata as metadata

# set up defaultdict representation
yaml.add_representer(defaultdict, Representer.represent_dict)

# can only have one of these at a time
MAJOR_PARTIES = ("Democratic", "Republican", "Independent")


PHONE_RE = re.compile(
    r"""^
                      \D*(1?)\D*                                # prefix
                      (\d{3})\D*(\d{3})\D*(\d{4}).*?             # main 10 digits
                      (?:(?:ext|Ext|EXT)\.?\s*\s*(\d{1,4}))?    # extension
                      $""",
    re.VERBOSE,
)


def reformat_phone_number(phone):
    match = PHONE_RE.match(phone)
    if match:
        groups = match.groups()

        ext = groups[-1]
        if ext:
            ext = f" ext. {ext}"
        else:
            ext = ""

        if not groups[0]:
            groups = groups[1:-1]
        else:
            groups = groups[:-1]
        return "-".join(groups) + ext
    else:
        return phone


def reformat_address(address):
    return re.sub(r"\s+", " ", re.sub(r"\s*\n\s*", ";", address))


def ocd_uuid(type):
    return "ocd-{}/{}".format(type, uuid.uuid4())


def get_data_dir(abbr):
    return os.path.join(os.path.dirname(__file__), "../data", abbr)


def get_all_abbreviations():
    return sorted(os.listdir(os.path.join(os.path.dirname(__file__), "../data")))


def get_jurisdiction_id(abbr):
    return metadata.lookup(abbr=abbr).jurisdiction_id


def load_yaml(file_obj):
    return yaml.load(file_obj, Loader=yamlordereddictloader.SafeLoader)


def iter_objects(abbr, objtype):
    filenames = glob.glob(os.path.join(get_data_dir(abbr), objtype, "*.yml"))
    for filename in filenames:
        with open(filename) as f:
            yield load_yaml(f), filename


def dump_obj(obj, *, output_dir=None, filename=None):
    if output_dir:
        filename = os.path.join(output_dir, get_filename(obj))
    if not filename:
        raise ValueError("must provide output_dir or filename parameter")
    with open(filename, "w") as f:
        yaml.dump(obj, f, default_flow_style=False, Dumper=yamlordereddictloader.SafeDumper)


def get_filename(obj):
    id = obj["id"].split("/")[1]
    name = obj["name"]
    name = re.sub(r"\s+", "-", name)
    name = re.sub(r"[^a-zA-Z-]", "", name)
    return f"{name}-{id}.yml"


def role_is_active(role):
    now = datetime.datetime.utcnow().date().isoformat()
    return str(role.get("end_date")) is None or str(role.get("end_date")) > now


def legacy_districts(**kwargs):
    """ can take jurisdiction_id or abbr via kwargs """
    legacy_districts = {"upper": [], "lower": []}
    for d in metadata.lookup(**kwargs).legacy_districts:
        legacy_districts[d.chamber_type].append(d.name)
    return legacy_districts


def load_municipalities(abbr):
    try:
        with open(os.path.join(get_data_dir(abbr), "municipalities.yml")) as f:
            return load_yaml(f)
    except FileNotFoundError:
        return []
