#!/usr/bin/env python
import os
import csv
import glob
import boto3
import click
from utils import (
    get_data_dir,
    get_jurisdiction_id,
    get_all_abbreviations,
    load_yaml,
    role_is_active,
)


def write_csv(files, jurisdiction_id, output_filename):
    with open(output_filename, "w") as outf:
        out = csv.DictWriter(
            outf,
            (
                "id",
                "name",
                "current_party",
                "current_district",
                "current_chamber",
                "given_name",
                "family_name",
                "gender",
                "email",
                "biography",
                "birth_date",
                "death_date",
                "image",
                "links",
                "sources",
                "capitol_address",
                "capitol_voice",
                "capitol_fax",
                "district_address",
                "district_voice",
                "district_fax",
                "twitter",
                "youtube",
                "instagram",
                "facebook",
            ),
        )
        out.writeheader()

        for filename in files:
            with open(filename) as f:
                data = load_yaml(f)

                # current party
                for role in data["party"]:
                    if role_is_active(role):
                        current_party = role["name"]
                        break

                # current district
                for role in data["roles"]:
                    if role_is_active(role):
                        current_chamber = role["type"]
                        current_district = role["district"]

                district_address = district_voice = district_fax = None
                capitol_address = capitol_voice = capitol_fax = None
                for cd in data.get("contact_details", {}):
                    note = cd["note"].lower()
                    if "district" in note:
                        district_address = cd.get("address")
                        district_voice = cd.get("voice")
                        district_fax = cd.get("fax")
                    elif "capitol" in note:
                        capitol_address = cd.get("address")
                        capitol_voice = cd.get("voice")
                        capitol_fax = cd.get("fax")
                    else:
                        click.secho("unknown office: " + note, fg="red")

                links = ";".join(k["url"] for k in data.get("links", []))
                sources = ";".join(k["url"] for k in data.get("sources", []))

                obj = {
                    "id": data["id"],
                    "name": data["name"],
                    "current_party": current_party,
                    "current_district": current_district,
                    "current_chamber": current_chamber,
                    "given_name": data.get("given_name"),
                    "family_name": data.get("family_name"),
                    "gender": data.get("gender"),
                    "email": data.get("email"),
                    "biography": data.get("biography"),
                    "birth_date": data.get("birth_date"),
                    "death_date": data.get("death_date"),
                    "image": data.get("image"),
                    "twitter": data.get("ids", {}).get("twitter"),
                    "youtube": data.get("ids", {}).get("youtube"),
                    "instagram": data.get("ids", {}).get("instagram"),
                    "facebook": data.get("ids", {}).get("facebook"),
                    "links": links,
                    "sources": sources,
                    "district_address": district_address,
                    "district_voice": district_voice,
                    "district_fax": district_fax,
                    "capitol_address": capitol_address,
                    "capitol_voice": capitol_voice,
                    "capitol_fax": capitol_fax,
                }
                out.writerow(obj)

    click.secho(f"processed {len(files)} files", fg="green")


@click.command()
@click.argument("abbreviations", nargs=-1)
@click.option("--upload/--no-upload", default=False, help="Upload to S3. (default: false)")
def to_csv(abbreviations, upload):
    """
    Sync YAML files to DB.
    """
    if not abbreviations:
        abbreviations = get_all_abbreviations()

    if upload:
        s3 = boto3.client("s3")

    for abbr in abbreviations:
        click.secho("==== {} ====".format(abbr), bold=True)
        directory = get_data_dir(abbr)
        jurisdiction_id = get_jurisdiction_id(abbr)
        person_files = sorted(glob.glob(os.path.join(directory, "legislature/*.yml")))
        fname = f"{abbr}.csv"
        write_csv(person_files, jurisdiction_id, fname)

        if upload:
            s3.upload_file(
                fname,
                "data.openstates.org",
                f"people/current/{abbr}.csv",
                ExtraArgs={"ContentType": "text/csv", "ACL": "public-read"},
            )
            click.secho(f"uploaded to data.openstates.org/people/current/{abbr}.csv", fg="green")


if __name__ == "__main__":
    to_csv()
