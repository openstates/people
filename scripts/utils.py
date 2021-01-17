import re
import os
import glob
import uuid
import datetime
from pathlib import Path
from typing import List
import yaml
import yamlordereddictloader
from collections import defaultdict, OrderedDict
from yaml.representer import Representer
from openstates import metadata

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


def get_data_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "../data"))


def get_data_dir(abbr: str, data_root='') -> str:
    return os.path.join(data_root or get_data_root(), abbr)


def get_all_abbreviations(data_root=''):
    return sorted(os.listdir(data_root or get_data_root()))


def get_jurisdiction_id(abbr):
    return metadata.lookup(abbr=abbr).jurisdiction_id


def load_yaml(file_obj):
    return yaml.load(file_obj, Loader=yamlordereddictloader.SafeLoader)


def load_yaml_path(p: str) -> OrderedDict:
    return load_yaml(Path(p).read_text())


def iter_objects(abbr, objtype):
    filenames = glob.glob(os.path.join(get_data_dir(abbr), objtype, "*.yml"))
    for filename in filenames:
        with open(filename) as f:
            yield load_yaml(f), filename


def dump_obj(obj, *, output_dir=None, filename=None):
    if output_dir:
        filename = os.path.join(output_dir, get_new_filename(obj))
    if not filename:
        raise ValueError("must provide output_dir or filename parameter")
    with open(filename, "w") as f:
        yaml.dump(obj, f, default_flow_style=False, Dumper=yamlordereddictloader.SafeDumper)


def get_new_filename(obj):
    id = obj["id"].split("/")[1]
    name = obj["name"]
    name = re.sub(r"\s+", "-", name)
    name = re.sub(r"[^a-zA-Z-]", "", name)
    return f"{name}-{id}.yml"

def person_filepath(person: dict, abbr: str, objtype: str, data_root='') -> str:
    return os.path.abspath(
        os.path.join(
            get_data_dir(abbr, data_root=data_root),
            objtype,
            get_new_filename(person)
        )
    )

def role_is_active(role, date=None):
    if not date:
        date = datetime.datetime.utcnow().date().isoformat()
    return (not role.get("end_date") or str(role.get("end_date")) > date) and (
        not role.get("start_date") or str(role.get("start_date")) <= date
    )


def find_file(leg_id, *, state="*"):
    if leg_id.startswith("ocd-person"):
        leg_id = leg_id.split("/")[1]
    assert len(leg_id) == 36
    files = glob.glob(os.path.join(get_data_dir(state), "*", f"*{leg_id}.yml"))
    if len(files) == 1:
        return files[0]
    elif len(files) > 1:
        raise ValueError(f"multiple files with same leg_id: {leg_id}")
    else:
        raise FileNotFoundError()


def legacy_districts(**kwargs):
    """ can take jurisdiction_id or abbr via kwargs """
    legacy_districts = {"upper": [], "lower": []}
    for d in metadata.lookup(**kwargs).legacy_districts:
        legacy_districts[d.chamber_type].append(d.name)
    return legacy_districts


def load_municipalities(abbr: str, data_root='') -> List[dict]:
    try:
        with open(
            os.path.join(
                get_data_dir(abbr, data_root=data_root),
                "municipalities.yml"
            )
        ) as f:
            return load_yaml(f)
    except FileNotFoundError:
        return []
