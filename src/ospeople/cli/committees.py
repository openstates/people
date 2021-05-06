import re
import sys
import json
import uuid
import typing
from functools import lru_cache
from pathlib import Path
from enum import Enum
from dataclasses import dataclass
from collections import defaultdict
import click
import yaml
from yaml.representer import Representer
from pydantic import ValidationError
from ..utils import get_data_dir, load_yaml, role_is_active
from ..models.committees import Committee, ScrapeCommittee

yaml.SafeDumper.add_representer(defaultdict, Representer.represent_dict)
yaml.SafeDumper.add_multi_representer(Enum, Representer.represent_str)


@dataclass
class DirectoryMergePlan:
    names_to_add: set[str]
    names_to_remove: set[str]
    same: int
    to_merge: list[tuple[Committee, ScrapeCommittee]]


class PersonMatcher:
    def __init__(self, abbr: str, directory: typing.Optional[Path] = None):
        self.abbr = abbr
        # chamber -> name piece -> id set
        self.current_people: dict[str, dict[str, set[str]]] = {"upper": {}, "lower": {}}
        self.all_ids: set[str] = set()

        # allow directory override for testing purposes
        if not directory:
            directory = Path(get_data_dir(abbr)) / "legislature"

        # read in people with current roles
        for filename in directory.glob("*.yml"):
            with open(filename) as file:
                person = load_yaml(file)
            chamber = ""
            for role in person["roles"]:
                if role_is_active(role):
                    chamber = typing.cast(str, role["type"])
                    break
            self.add_name(chamber, person["name"], person["id"])
            if person.get("family_name"):
                self.add_name(chamber, person["family_name"], person["id"])
            for name in person.get("other_names", []):
                self.add_name(chamber, name["name"], person["id"])

    def add_name(self, chamber: str, name_piece: str, id_: str) -> None:
        self.all_ids.add(id_)
        if name_piece in self.current_people[chamber]:
            self.current_people[chamber][name_piece].add(id_)
        else:
            self.current_people[chamber][name_piece] = {id_}

    @lru_cache(500)
    def match(self, chamber: str, name: str) -> typing.Optional[str]:
        candidates = self.current_people[chamber].get(name, None)
        if not candidates:
            click.secho(f"  no candidates while attempting to match {chamber} {name}", fg="yellow")
            return None
        elif len(candidates) == 1:
            return list(candidates)[0]
        else:
            click.secho(
                f"  multiple candidates while attempting to match {chamber} {name}", fg="yellow"
            )
            return None

    def id_exists(self, id_: str) -> bool:
        return id_ in self.all_ids


def merge_lists(orig: list, new: list, key_attr: str) -> list:
    """ merge two lists based on a unique property """
    combined = []
    new_by_key = {getattr(item, key_attr): item for item in new}
    seen = set()
    # add original items, or their replacements if present
    for item in orig:
        key = getattr(item, key_attr)
        seen.add(key)
        if key in new_by_key:
            combined.append(new_by_key[key])
        else:
            combined.append(item)
    # add new items
    for key, item in new_by_key.items():
        if key not in seen:
            combined.append(item)
    return combined


def merge_committees(orig: Committee, new: Committee) -> Committee:
    # disallow merge of these, likely error & unclear what should happen
    if orig.parent != new.parent:
        raise ValueError("cannot merge committees with different parents")
    if orig.classification != new.classification:
        raise ValueError("cannot merge committees with different classifications")
    if orig.jurisdiction != new.jurisdiction:
        raise ValueError("cannot merge committees with different jurisdictions")

    merged = Committee(
        id=orig.id,  # id stays constant
        parent=orig.parent,
        classification=orig.classification,
        jurisdiction=orig.jurisdiction,
        name=new.name,  # name can be updated
        sources=merge_lists(orig.sources, new.sources, "url"),
        links=merge_lists(orig.links, new.links, "url"),
        other_names=merge_lists(orig.other_names, new.other_names, "name"),
        members=merge_lists(orig.members, new.members, "name"),
    )
    return merged


class CommitteeDir:
    def __init__(
        self, abbr: str, raise_errors: bool = True, directory: typing.Optional[Path] = None
    ):
        self.abbr = abbr
        # allow overriding directory explicitly, useful for testing
        self.directory = directory if directory else Path(get_data_dir(abbr)) / "committees"
        # chamber -> name -> Committee
        self.coms_by_chamber_and_name: defaultdict[str, dict[str, Committee]] = defaultdict(dict)
        self.errors = []

        # make sure a committees dir exists
        self.directory.mkdir(parents=True, exist_ok=True)

        for filename in self.directory.glob("*.yml"):
            with open(filename) as file:
                data = load_yaml(file)
                try:
                    com = Committee(**data)
                    self.coms_by_chamber_and_name[com.parent][com.name] = com
                except ValidationError as ve:
                    if raise_errors:
                        raise
                    self.errors.append((filename, ve))

        # prepare person matcher
        self.person_matcher = PersonMatcher(self.abbr)

    def get_new_filename(self, obj: Committee) -> str:
        id = obj.id.split("/")[1]
        name = re.sub(r"\s+", "-", obj.name)
        name = re.sub(r"[^a-zA-Z-]", "", name)
        return f"{obj.parent}-{name}-{id}.yml"

    def get_filename_by_id(self, com_id: str) -> Path:
        if com_id.startswith("ocd-organization"):
            com_id = com_id.split("/")[1]
        assert len(com_id) == 36
        files = list(self.directory.glob(f"*{com_id}.yml"))
        if len(files) == 1:
            return files[0]
        else:
            raise FileNotFoundError()

    def get_filename_by_name(self, chamber: str, name: str) -> Path:
        try:
            com = self.coms_by_chamber_and_name[chamber][name]
        except KeyError:
            raise FileNotFoundError()
        return self.get_filename_by_id(com.id)

    def save_committee(self, committee: Committee) -> None:
        # try to use id's existing filename if possible
        try:
            filename = self.get_filename_by_id(committee.id)
        except FileNotFoundError:
            filename = self.directory / self.get_new_filename(committee)

        with open(filename, "w") as f:
            yaml.dump(
                committee.to_dict(),
                f,
                default_flow_style=False,
                Dumper=yaml.SafeDumper,
                sort_keys=False,
            )

    def add_committee(self, committee: ScrapeCommittee) -> None:
        # convert a ScrapeCommittee to a committee by giving it an ID
        full_com = Committee(id=f"ocd-organization/{uuid.uuid4()}", **committee.dict())
        self.coms_by_chamber_and_name[committee.parent][committee.name] = committee
        self.save_committee(full_com)

    def ingest_scraped_json(self, input_dir: str) -> list[ScrapeCommittee]:
        scraped_data = []
        for filename in Path(input_dir).glob("*"):
            with open(filename) as file:
                data = json.load(file)
                com = ScrapeCommittee(**data)
                # do person matching on import so that diffs work
                for member in com.members:
                    mid = self.person_matcher.match(com.parent, member.name)
                    if mid:
                        member.person_id = mid
                scraped_data.append(com)
        return scraped_data

    def get_merge_plan_by_chamber(
        self, chamber: str, new_data: list[ScrapeCommittee]
    ) -> DirectoryMergePlan:
        existing_names = set(self.coms_by_chamber_and_name[chamber].keys())
        new_names = {com.name for com in new_data}

        names_to_add = new_names - existing_names
        names_to_remove = existing_names - new_names
        names_to_compare = new_names & existing_names
        to_merge = list()
        same = 0

        for com in new_data:
            if com.name in names_to_compare:
                # reverse a saved Committee to a ScrapeCommittee for comparison
                existing = self.coms_by_chamber_and_name[chamber][com.name]
                com_without_id = existing.dict()
                com_without_id.pop("id")
                com_without_id.pop("jurisdiction")
                rev_sc = ScrapeCommittee(**com_without_id)
                if com != rev_sc:
                    to_merge.append((existing, com))
                else:
                    same += 1

        return DirectoryMergePlan(
            names_to_add=names_to_add,
            names_to_remove=names_to_remove,
            same=same,
            to_merge=to_merge,
        )


@click.group()
def main() -> None:
    pass


@main.command()  # pragma: no cover
@click.argument("abbr")
@click.argument("input_dir")
def merge(abbr: str, input_dir: str) -> None:
    """
    Convert scraped committee JSON in INPUT_DIR to YAML files for this repo.
    """
    comdir = CommitteeDir(abbr)

    coms_by_chamber: defaultdict[str, list[ScrapeCommittee]] = defaultdict(list)
    scraped_data = comdir.ingest_scraped_json(input_dir)
    for com in scraped_data:
        coms_by_chamber[com.parent].append(com)

    for chamber, coms in coms_by_chamber.items():
        plan = comdir.get_merge_plan_by_chamber(chamber, coms)

        click.secho(
            f"{len(plan.names_to_add)} to add", fg="yellow" if plan.names_to_add else "green"
        )
        click.secho(
            f"{len(plan.names_to_remove)} to remove",
            fg="yellow" if plan.names_to_remove else "green",
        )
        click.secho(f"{plan.same} without changes", fg="green")
        click.secho(
            f"{len(plan.to_merge)} with changes", fg="yellow" if plan.to_merge else "green"
        )

        if plan.names_to_add or plan.names_to_remove or plan.to_merge:
            if not click.confirm("Do you wish to continue?"):
                sys.exit(1)

            # add new committees
            for com in coms:
                if com.name in plan.names_to_add:
                    comdir.add_committee(com)
                    click.secho(f"  adding {com.parent} {com.name}")

            # remove old committees
            for name in plan.names_to_remove:
                filename = comdir.get_filename_by_name(chamber, name)
                click.secho(f"removing {filename}", fg="red")
                filename.unlink()

            # merge remaining committees
            for orig, new in plan.to_merge:
                merged = merge_committees(orig, new)
                comdir.save_committee(merged)
        else:
            click.secho("nothing to do!", fg="green")


@main.command()  # pragma: no cover
@click.argument("abbr")
def lint(abbr: str) -> None:
    """
    Convert scraped committee JSON in INPUT_DIR to YAML files for this repo.
    """
    comdir = CommitteeDir(abbr, raise_errors=False)
    errors = 0
    click.secho(f"==== {abbr} ====")
    for filename, error in comdir.errors:
        click.secho(filename.name)
        for error in error.errors():
            click.secho(f"  {'.'.join(str(l) for l in error['loc'])}: {error['msg']}", fg="red")
            errors += 1
    if errors:
        click.secho(f"exiting with {errors} errors", fg="red")
        sys.exit(1)


if __name__ == "__main__":
    main()
