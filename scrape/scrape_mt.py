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
from common import Person


# Montana-specific


def clean_name(name):
    name = re.sub(r"\s+", " ", name)
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
        url = str(name.xpath("a/@href")[0])

        person = Person(
            name=clean_name(name.text_content()),
            state="mt",
            party=party.text_content().strip(),
            chamber=("upper" if chamber == "SD" else "lower"),
            district=district,
        )
        person.add_link(url)
        person.add_source(url)

        phone = phone.text_content().strip()
        if len(phone) == 14:
            person.capitol_office.voice = phone
        elif len(phone) > 30:
            person.capitol_office.voice = phone.split("    ")[0]

        email = email.xpath("./a/@href")
        if email:
            email = email[0].split(":", 1)[1]
        person.capitol_office.email = email

        return person, url

    # def add_details(self, person, url):
    #     doc = self.lxmlize(url)
    # TODO: add image & address, need to solve base64 issue


def main():
    try:
        os.makedirs("incoming/mt/people")
    except OSError:
        pass
    mt = MontanaScraper()
    for leg in mt.scrape_legislator_list("113"):
        leg.save("incoming/mt/people")


if __name__ == "__main__":
    main()
