#!/usr/bin/env python
"""
Prototype new-style scraper for direct-to-YAML scraping of Montana

These classes would be abstracted to a helper library of course, but the gist
is to replicate something like pupa but much simpler.
"""
import scrapelib
import lxml.html
import re
import os
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


# Montana-specific

def clean_name(name):
    name = re.sub('\s+', ' ', name)
    name = name.strip()
    return name.title()


class MontanaScraper(scrapelib.Scraper):

    def lxmlize(self, url):
        data = self.get(url)
        doc = lxml.html.fromstring(data.content)
        doc.make_links_absolute(url)
        return doc

    def scrape_legislator_list(self, session_num):
        url = "https://leg.mt.gov/legislator-information/?session_select=" + session_num
        list_xpath = "//table[1]/tbody/tr"
        for line in self.lxmlize(url).xpath(list_xpath):
            person, url = self.handle_list_item(line)
            yield person

    def handle_list_item(self, item):
        tds = item.getchildren()
        email, name, party, seat, phone = tds

        chamber, district = seat.text_content().strip().split()
        url = str(name.xpath('a/@href')[0])

        person = Person(
            name=clean_name(name.text_content()),
            state='mt',
            party=party.text_content().strip(),
            chamber=('upper' if chamber == 'SD' else 'lower'),
            district=district,
        )
        person.add_link(url)
        person.add_source(url)

        phone = phone.text_content().strip()
        if len(phone) == 14:
            person.capitol_office.voice = phone
        elif len(phone) > 30:
            person.capitol_office.voice = phone.split('    ')[0]

        email = email.xpath('./a/@href')
        if email:
            email = email[0].split(':', 1)[1]
        person.capitol_office.email = email

        return person, url

    # def add_details(self, person, url):
    #     doc = self.lxmlize(url)
    # TODO: add image & address, need to solve base64 issue


def main():
    try:
        os.makedirs('incoming/mt/people')
    except OSError:
        pass
    mt = MontanaScraper()
    for leg in mt.scrape_legislator_list('113'):
        leg.save('incoming/mt/people')


if __name__ == '__main__':
    main()
