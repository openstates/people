import csv
from ..utils import find_file, load_yaml, dump_obj

with open("nyleg.csv") as f:
    for row in csv.DictReader(f):
        os_id = row["osid"]
        fname = find_file(os_id)
        with open(fname) as lf:
            obj = load_yaml(lf)
            for cd in obj["contact_details"]:
                if cd["note"] == "Capitol Office":
                    cd["voice"] = row["Capitol Phone"].replace("(", "").replace(") ", "-")
                if cd["note"] == "District Office":
                    cd["voice"] = row["District Phone"].replace("(", "").replace(") ", "-")
            obj["email"] = row["email"]
            if row["twitter"] and "ids" not in obj:
                obj["ids"] = {"twitter": row["twitter"].replace("@", "")}
        dump_obj(obj, filename=fname)
