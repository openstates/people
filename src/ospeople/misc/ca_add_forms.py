import glob
from ..utils import load_yaml, dump_obj, role_is_active

for file in glob.glob("data/ca/legislature/*.yml"):
    with open(file) as inf:
        data = load_yaml(inf)
        for role in data["roles"]:
            if role_is_active(role):
                letter = "A" if role["type"] == "lower" else "S"
                district = int(role["district"])
        url = f"https://lcmspubcontact.lc.ca.gov/PublicLCMS/ContactPopup.php?district={letter}D{district:02d}&inframe=N"
        data["links"].append(
            {"url": url, "note": "Contact Form"},
        )
        dump_obj(data, filename=file)
