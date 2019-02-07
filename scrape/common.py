import uuid
from collections import OrderedDict
from utils import dump_obj, get_jurisdiction_id, reformat_phone_number

PARTIES = {'d': 'Democratic',
           'r': 'Republican',
           'dem': 'Democratic',
           'rep': 'Republican',
           'democrat': 'Democratic',
           'republican': 'Republican',
           }


class ContactDetail:
    def __init__(self, note):
        self.note = note
        self.voice = None
        self.email = None
        self.fax = None
        self.address = None

    def to_dict(self):
        d = {}
        for key in ('voice', 'email', 'fax', 'address'):
            val = getattr(self, key)
            if val:
                if key in ('voice', 'fax'):
                    val = reformat_phone_number(val)
                d[key] = val
        if d:
            d["note"] = self.note
        return d


class Person:
    def __init__(self, name, *,
                 state, party, district, chamber,
                 image=None, given_name=None, family_name=None):
        self.name = name
        self.party = party
        self.district = district
        self.chamber = chamber
        self.state = state
        self.given_name = given_name
        self.family_name = family_name
        self.image = image
        self.links = []
        self.sources = []
        self.capitol_office = ContactDetail('Capitol Office')
        self.district_office = ContactDetail('District Office')

    def to_dict(self):
        party = PARTIES.get(self.party.lower(), self.party)
        d = OrderedDict({
            "id": f"ocd-person/{uuid.uuid4()}",
            "name": self.name,
            "party": [{"name": party}],
            "roles": [{"district": self.district,
                       "type": self.chamber,
                       "jurisdiction": get_jurisdiction_id(self.state),
                       }],
            "links": self.links,
            "sources": self.sources,
        })
        if self.given_name:
            d["given_name"] = self.given_name
        if self.family_name:
            d["family_name"] = self.family_name
        if self.image:
            d["image"] = self.image

        # contact details
        d["contact_details"] = []
        if self.district_office.to_dict():
            d["contact_details"].append(self.district_office.to_dict())
        if self.capitol_office.to_dict():
            d["contact_details"].append(self.capitol_office.to_dict())

        return d

    def save(self, directory):
        dump_obj(self.to_dict(), output_dir=directory)

    def add_link(self, url, note=None):
        if note:
            self.links.append({'url': url, 'note': note})
        else:
            self.links.append({'url': url})

    def add_source(self, url, note=None):
        if note:
            self.sources.append({'url': url, 'note': note})
        else:
            self.sources.append({'url': url})
