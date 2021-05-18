import re
import os
import uuid
import datetime
import typing
import yaml
import yamlordereddictloader  # type: ignore
from pathlib import Path
from enum import Enum
from collections import defaultdict
from yaml.representer import Representer
from openstates import metadata

# set up defaultdict representation
yaml.add_representer(defaultdict, Representer.represent_dict)
yamlordereddictloader.SafeDumper.add_multi_representer(Enum, Representer.represent_str)


def ocd_uuid(type: str) -> str:
    return "ocd-{}/{}".format(type, uuid.uuid4())


def get_data_dir(abbr: str) -> str:
    return os.path.join(os.path.dirname(__file__), "../../../data", abbr)


def get_data_path(abbr: str) -> Path:
    # 4 parent calls to get from this file to /data dir
    return Path(__file__).parent.parent.parent.parent / "data" / abbr


def load_settings() -> dict:
    settings_file = os.path.join(os.path.dirname(__file__), "../../../settings.yml")
    with open(settings_file) as f:
        return load_yaml(f)


def get_all_abbreviations() -> list[str]:
    return sorted(os.listdir(os.path.join(os.path.dirname(__file__), "../../../data")))


def load_yaml(file_obj: typing.TextIO) -> dict:
    return yaml.load(file_obj, Loader=yamlordereddictloader.SafeLoader)


def iter_objects(abbr: str, objtype: str) -> typing.Iterator[tuple[dict, str]]:
    filenames = (get_data_path(abbr) / objtype).glob("*.yml")
    for filename in filenames:
        with open(filename) as f:
            yield load_yaml(f), filename


def dump_obj(
    obj: dict, *, output_dir: typing.Optional[str] = None, filename: typing.Optional[str] = None
) -> None:
    if output_dir:
        filename = os.path.join(output_dir, get_new_filename(obj))
    if not filename:
        raise ValueError("must provide output_dir or filename parameter")
    with open(filename, "w") as f:
        yaml.dump(
            obj,
            f,
            default_flow_style=False,
            Dumper=yamlordereddictloader.SafeDumper,
            sort_keys=False,
        )


def get_new_filename(obj: dict) -> str:
    id = obj["id"].split("/")[1]
    name = obj["name"]
    name = re.sub(r"\s+", "-", name)
    name = re.sub(r"[^a-zA-Z-]", "", name)
    return f"{name}-{id}.yml"


def role_is_active(role: dict, date: typing.Optional[str] = None) -> bool:
    if date is None:
        date = datetime.datetime.utcnow().date().isoformat()
    return (role.get("end_date") is None or str(role.get("end_date")) > date) and (
        role.get("start_date") is None or str(role.get("start_date")) <= date
    )


def find_file(leg_id: str, *, state: str = "*") -> str:
    if leg_id.startswith("ocd-person"):
        leg_id = leg_id.split("/")[1]
    assert len(leg_id) == 36

    if state == "*":
        filedir = Path(get_data_dir("."))
        files = list(filedir.glob(f"*/*/*{leg_id}.yml"))
    else:
        filedir = Path(get_data_dir(state))
        files = list(filedir.glob(f"*/*{leg_id}.yml"))

    if len(files) == 1:
        return files[0]
    elif len(files) > 1:
        raise ValueError(f"multiple files with same leg_id: {leg_id}")
    else:
        raise FileNotFoundError()


def legacy_districts(
    abbr: typing.Optional[str] = None, jurisdiction_id: typing.Optional[str] = None
) -> dict[str, list[str]]:
    """ can take jurisdiction_id or abbr via kwargs """
    legacy_districts: dict[str, list[str]] = {"upper": [], "lower": []}
    for d in metadata.lookup(abbr=abbr, jurisdiction_id=jurisdiction_id).legacy_districts:
        legacy_districts[d.chamber_type].append(d.name)
    return legacy_districts


def load_municipalities(abbr: str) -> list[dict]:
    try:
        with open(os.path.join(get_data_dir(abbr), "municipalities.yml")) as f:
            return typing.cast(list, load_yaml(f))
    except FileNotFoundError:
        return []
