#!/usr/bin/env python
"""
Prototype new-style scraper for direct-to-YAML scraping of Alaska
"""
import scrapelib
import lxml.etree
import re
import os
from common import Person


def clean_name(name):
    name = re.sub(r'\s+', ' ', name)
    name = name.strip()
    return name.title()

ELEMENTS = (
    'FirstName',
    'MiddleName',
    'LastName',
    'EMail',
    'Phone',
    'District',
    'Party',
    'Building',
    'Room',
)


def _get_if_exists(item, elem):
    val = item.xpath(f"./{elem}/text()")
    if val:
        return str(val[0])


class AlaskaScraper(scrapelib.Scraper):

    def scrape_legislator_list(self, session_num):
        url = "http://www.legis.state.ak.us/publicservice/basis/members?minifyresult=false&session=" + session_num
        xml = scrapelib.Scraper().get(url).content
        for line in lxml.etree.fromstring(xml).xpath("//Member/MemberDetails"):
            person = self.handle_list_item(line, session_num)
            yield person

    def handle_list_item(self, item, session_num):
        item_dict = {
            elem: _get_if_exists(item, elem) for elem in ELEMENTS
        }
        chamber = item.attrib["chamber"]
        code = item.attrib["code"].lower()

        person = Person(
            name="{FirstName} {LastName}".format(**item_dict),
            given_name=item_dict['FirstName'],
            family_name=item_dict['LastName'],
            state='ak',
            party=item_dict["Party"],
            chamber=('upper' if chamber == 'S' else 'lower'),
            district=item_dict["District"],
            image=f"http://akleg.gov/images/legislators/{code}.jpg"
        )
        person.add_link("http://www.akleg.gov/basis/Member/Detail/{}?code={}".format(
            session_num,
            code,
        ))
        person.add_source("http://w3.akleg.gov/")

        phone = "907-" + item_dict["Phone"][0:3] + "-" + item_dict["Phone"][3:]
        person.capitol_office.voice = phone
        person.capitol_office.email = item_dict["EMail"]

        if item_dict["Building"] == "CAPITOL":
            person.capitol_office.address = "State Capitol Room {}; Juneau AK, 99801".format(
                item_dict["Room"]
            )

        return person


def main():
    try:
        os.makedirs('incoming/ak/people')
    except OSError:
        pass
    ak = AlaskaScraper()
    for leg in ak.scrape_legislator_list('31'):
        leg.save('incoming/ak/people')


if __name__ == '__main__':
    main()
