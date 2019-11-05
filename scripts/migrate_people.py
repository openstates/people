#!/usr/bin/env python
import sys
import os
import glob
import itertools
import json
from collections import defaultdict
from utils import ocd_uuid, get_jurisdiction_id, get_data_dir, dump_obj, iter_objects


OLD_DATA_DIRECTORY = "/Users/james/Desktop/old-json-to-new/old"


def load_new_files(state):
    new_db_ids = set()

    for data, _ in itertools.chain(iter_objects(state, "people"), iter_objects(state, "retired")):
        for ids in data.get("other_identifiers", []):
            if ids["scheme"] == "legacy_openstates":
                new_db_ids.add(ids["identifier"])

    print("found", len(new_db_ids), "migrated ids")
    return new_db_ids


def scan_old_files(state, new_db_ids):
    with open(os.path.join(OLD_DATA_DIRECTORY, state, "metadata.json")) as f:
        metadata = json.load(f)

    all_old_files = glob.glob(os.path.join(OLD_DATA_DIRECTORY, state, "legislators/*"))
    for f in all_old_files:
        data = json.load(open(f))

        found = 0
        for oid in data["_all_ids"]:
            if oid in new_db_ids:
                found += 1
        if found == 0:
            process_old_file(f, metadata)
        elif found == len(data["_all_ids"]):
            print("ALREADY MIGRATED:", f)
        else:
            print("!!! PARTIAL:", f)


def terms_to_roles(leg_terms, metadata_terms):
    # term_id => (start, end)
    term_ranges = {}
    for mt in metadata_terms:
        term_ranges[mt["name"]] = (mt["start_year"], mt["end_year"])

    # (chamber, district) => [years]
    years_for_position = defaultdict(list)
    for lt in leg_terms:
        start, end = term_ranges[lt["term"]]
        years_for_position[(lt["chamber"], lt["district"])].extend(
            list(range(start, end + 1))
        )

    positions = []

    for pos, years in years_for_position.items():
        years = sorted(years)
        start_year = None
        prev_year = start_year = years[0]
        for year in years[1:]:
            if year != prev_year + 1:
                positions.append((*pos, start_year, prev_year))
                start_year = year
            prev_year = year

        positions.append((*pos, start_year, prev_year))

    return positions


def process_old_file(filename, metadata):
    data = json.load(open(filename))
    if data["leg_id"] != data["_id"]:
        raise Exception()
    if data.get("active"):
        raise Exception()
    if data.get("roles", []):
        raise Exception()

    # remove unused fields
    for k in (
        "_yearly_contributions",
        "nimsp_candidate_id",
        "votesmart_id",
        "_contributions_start_year",
        "_scraped_name",
        "_total_contributions",
        "transparencydata_id",
        "_locked_fields",
        "level",
        "nimsp_id",
        "_type",
        "country",
        "updated_at",
        "_id",
        "active",
        "roles",
        "offices",
        "notice",
        "nickname",
        "district",
        "party",
        "chamber",
        "csrfmiddlewaretoken",
        "email",
        "created_at",
    ):
        data.pop(k, None)

    # remove plus fields
    for k in [k for k in data.keys() if k.startswith("+")]:
        data.pop(k)

    leg_obj = {
        "id": ocd_uuid("person"),
    }

    leg_obj["name"] = data.pop("full_name")
    first_name = data.pop("first_name")
    middle_name = data.pop("middle_name")
    last_name = data.pop("last_name")
    suffixes = data.pop("suffixes", "")
    suffix = data.pop("suffix", "")
    if first_name:
        leg_obj["given_name"] = first_name
    if last_name:
        leg_obj["family_name"] = last_name
    if middle_name:
        leg_obj["middle_name"] = middle_name
    if suffix:
        leg_obj["suffix"] = suffixes or suffix

    state = data.pop("state")
    jurisdiction_id = get_jurisdiction_id(state)

    # pull useful fields
    old_roles = data.pop("old_roles", {})
    parties = set()
    new_roles = []
    for session, roles in old_roles.items():
        for role in roles:
            if "committee_id" in role:
                continue
            parties.add(role["party"])
            new_roles.append(
                {
                    "term": role["term"],
                    "chamber": role["chamber"],
                    "district": role["district"],
                }
            )

    leg_obj["party"] = [{"name": party} for party in parties]

    # add these to leg_obj
    roles = terms_to_roles(new_roles, metadata["terms"])
    formatted_roles = []
    for chamber, district, start, end in roles:
        formatted_roles.append({
            "district": district,
            "jurisdiction": jurisdiction_id,
            "type": chamber,
            "start_date": f"{start}-01-01",
            "end_date": f"{end}-12-31",
        })
    leg_obj["roles"] = formatted_roles

    all_ids = data.pop("_all_ids")
    leg_id = data.pop("leg_id")
    if leg_id not in all_ids:
        all_ids.append(leg_id)

    image = data.pop("photo_url", "")
    if image:
        leg_obj["image"] = image
    url = data.pop("url", "")
    if url:
        leg_obj["links"] = [{"url": url}]
    leg_obj["sources"] = data.pop("sources")
    leg_obj["other_identifiers"] = [
        {"identifier": id_, "scheme": "legacy_openstates"} for id_ in all_ids
    ]

    if data:
        print(data)
        raise Exception()

    print(leg_obj)


def main():
    state = sys.argv[1]
    new_ids = load_new_files(state)
    scan_old_files(state, new_ids)


main()
