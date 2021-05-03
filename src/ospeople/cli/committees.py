import os
import re
import glob
import json
import uuid
from collections import defaultdict
import click
from pydantic import ValidationError
from ..utils import get_data_dir, load_yaml, dump_obj
from ..models.committees import Committee, ScrapeCommittee


class CommitteeDir:
    def __init__(self, abbr, raise_errors=True):
        data_dir = get_data_dir(abbr)
        self.directory = os.path.join(data_dir, "committees")
        self.coms_by_chamber_and_name: defaultdict[str, dict[str, Committee]] = defaultdict(dict)
        self.errors = []

        # make sure a committees dir exists
        try:
            os.makedirs(self.directory)
        except FileExistsError:
            pass

        for filename in glob.glob(os.path.join(self.directory, "*.yml")):
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
        # TODO: fix key order
        dump_obj(
            committee.dict(),
            filename=os.path.join(self.directory, self.get_new_filename(committee)),
        )

    def add_committee(self, committee: ScrapeCommittee) -> None:
        full_com = Committee(id=f"ocd-organization/{uuid.uuid4()}", **committee.dict())
        self.coms_by_chamber_and_name[committee.parent][committee.name] = committee
        self.save_committee(full_com)


def ingest_scraped_json(input_dir: str) -> list[Committee]:
    scraped_data = []
    for filename in glob.glob(os.path.join(input_dir, "*")):
        with open(filename) as file:
            data = json.load(file)
            com = ScrapeCommittee(**data)
            scraped_data.append(com)
    return scraped_data


def merge_data(committee_dir, incoming):
    coms_by_chamber: defaultdict[str, list[Committee]] = defaultdict(list)

    for com in incoming:
        coms_by_chamber[com.parent].append(com)

    for chamber, coms in coms_by_chamber.items():
        merge_data_by_chamber(committee_dir, chamber, coms)


def merge_data_by_chamber(committee_dir: CommitteeDir, chamber: str, new_data: list[CommitteeDir]):
    existing_names = set(committee_dir.coms_by_chamber_and_name[chamber].keys())
    new_names = {com.name for com in new_data}

    names_to_add = new_names - existing_names
    names_to_remove = existing_names - new_names
    names_to_compare = new_names & existing_names
    to_merge = list()
    same = 0

    # TODO: prettify & prompt to continue
    print(f"{len(names_to_add)} to add")
    print(f"{len(names_to_remove)} to remove")

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

    print(f"{same} without changes")
    print(f"{len(to_merge)} with changes")

    for com in new_data:
        if com.name in names_to_add:
            committee_dir.add_committee(com)

    # TODO: names_to_remove
    # TODO: to_merge


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
    scraped_data = ingest_scraped_json(input_dir)

    merge_data(comdir, scraped_data)


@main.command()  # pragma: no cover
@click.argument("abbr")
def lint(abbr: str) -> None:
    """
    Convert scraped committee JSON in INPUT_DIR to YAML files for this repo.
    """
    comdir = CommitteeDir(abbr, raise_errors=False)
    for filename, error in comdir.errors:
        print(os.path.basename(filename))
        for error in error.errors():
            print(f"  {'.'.join(str(l) for l in error['loc'])}: {error['msg']}")


if __name__ == "__main__":
    main()
