import re
import os
import uuid
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


def get_data_path(abbr: str) -> Path:
    # 4 parents up to get from this file to /data dir
    return Path(__file__).parents[3] / "data" / abbr


def get_all_abbreviations() -> list[str]:
    return sorted(x.name for x in (Path(__file__).parents[3] / "data").iterdir())


def dump_obj(
    obj: dict,
    *,
    output_dir: typing.Union[Path] = None,
    filename: typing.Union[Path, str, None] = None,
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
        with open(get_data_path(abbr) / "municipalities.yml") as f:
            return typing.cast(list, yaml.safe_load(f))
    except FileNotFoundError:
        return []
