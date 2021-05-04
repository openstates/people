import re
import sys
import json
import uuid
from pathlib import Path
from enum import Enum
from dataclasses import dataclass
from collections import defaultdict
import click
import yaml
from yaml.representer import Representer
from pydantic import ValidationError
from ..utils import get_data_dir, load_yaml
from ..models.committees import Committee, ScrapeCommittee

yaml.SafeDumper.add_representer(defaultdict, Representer.represent_dict)
yaml.SafeDumper.add_multi_representer(Enum, Representer.represent_str)


def get_active_person_names(abbr: str):
    pass


class CommitteeDir:
    def __init__(self, abbr: str, raise_errors: bool = True):
        data_dir = get_data_dir(abbr)
        self.directory = Path(data_dir) / "committees"
        self.coms_by_chamber_and_name: defaultdict[str, dict[str, Committee]] = defaultdict(dict)
        self.errors = []

        # make sure a committees dir exists
        self.directory.mkdir(parents=True, exist_ok=True)

        for filename in self.directory.glob("*.yml"):
            with open(filename) as file:
                data = load_yaml(file)
                try:
                    com = Committee(**data)
                except ValidationError as ve:
                    if raise_errors:
                        raise
                    self.errors.append((filename, ve))
                self.coms_by_chamber_and_name[com.parent][com.name] = com

    def get_new_filename(self, obj: Committee) -> str:
        id = obj.id.split("/")[1]
        name = re.sub(r"\s+", "-", obj.name)
        name = re.sub(r"[^a-zA-Z-]", "", name)
        return f"{obj.parent}-{name}-{id}.yml"

    def save_committee(self, committee: Committee) -> None:
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
        # convert a ScrapeCommittee to a committee by giving it an ID and trying to match names
        full_com = Committee(id=f"ocd-organization/{uuid.uuid4()}", **committee.dict())
        self.coms_by_chamber_and_name[committee.parent][committee.name] = committee
        self.save_committee(full_com)


def ingest_scraped_json(input_dir: str) -> list[Committee]:
    scraped_data = []
    for filename in Path(input_dir).glob("*"):
        with open(filename) as file:
            data = json.load(file)
            com = ScrapeCommittee(**data)
            scraped_data.append(com)
    return scraped_data


@dataclass
class DirectoryMergePlan:
    names_to_add: set[str]
    names_to_remove: set[str]
    same: int
    to_merge: list[tuple[Committee, ScrapeCommittee]]


def get_merge_plan_by_chamber(
    committee_dir: CommitteeDir, chamber: str, new_data: list[ScrapeCommittee]
) -> DirectoryMergePlan:
    existing_names = set(committee_dir.coms_by_chamber_and_name[chamber].keys())
    new_names = {com.name for com in new_data}

    names_to_add = new_names - existing_names
    names_to_remove = existing_names - new_names
    names_to_compare = new_names & existing_names
    to_merge = list()
    same = 0

    for com in new_data:
        if com.name in names_to_compare:
            # reverse a saved Committee to a ScrapeCommittee for comparison
            existing = committee_dir.coms_by_chamber_and_name[chamber][com.name]
            com_without_id = existing.dict()
            com_without_id.pop("id")
            rev_sc = ScrapeCommittee(**com_without_id)
            if com != rev_sc:
                to_merge.append((existing, com))
            else:
                same += 1

    return DirectoryMergePlan(
        names_to_add=names_to_add, names_to_remove=names_to_remove, same=same, to_merge=to_merge
    )


def merge_new_files(
    committee_dir: CommitteeDir, new_data: list[Committee], names_to_add: set[str]
) -> None:
    for com in new_data:
        if com.name in names_to_add:
            committee_dir.add_committee(com)
            click.secho(f"  adding {com.parent} {com.name}")


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
    scraped_data = ingest_scraped_json(input_dir)
    for com in scraped_data:
        coms_by_chamber[com.parent].append(com)

    for chamber, coms in coms_by_chamber.items():
        plan = get_merge_plan_by_chamber(comdir, chamber, coms)

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
            merge_new_files(comdir, scraped_data, plan.names_to_add)

            # TODO: names_to_remove
            for name in plan.names_to_remove:
                print(name)

            # TODO: to_merge
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
