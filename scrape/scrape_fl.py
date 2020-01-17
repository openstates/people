#!/usr/bin/env python
"""
Prototype new-style scraper for direct-to-YAML scraping of Florida
"""
import re
import os
import logging
from common import Person
from scrape_tools import ListPage, Page

log = logging.getLogger("fl")


def fix_name(name):
    # handles cases like Watson, Jr., Clovis
    if ", " not in name:
        return name
    last, first = name.rsplit(", ", 1)
    return first + " " + last


class SenDetail(Page):
    def get_url(self):
        return self.obj.links[0]["url"]

    def handle_page(self):
        email = self.doc.xpath('//a[contains(@href, "mailto:")]')[0].get("href").split(":")[-1]
        self.obj.capitol_office.email = email
        self.obj.image = str(self.doc.xpath('//div[@id="sidebar"]//img/@src').pop())


class SenContactDetail(ListPage):
    list_xpath = '//h4[contains(text(), "Office")]'

    def get_url(self):
        return self.obj.links[0]["url"]

    def handle_list_item(self, office):
        (name,) = office.xpath("text()")
        print(name)
        if name == "Tallahassee Office":
            obj_office = self.obj.capitol_office
        else:
            obj_office = self.obj.district_office

        address_lines = [
            x.strip()
            for x in office.xpath("following-sibling::div[1]")[0].text_content().splitlines()
            if x.strip()
        ]

        clean_address_lines = []
        fax = phone = None
        PHONE_RE = r"\(\d{3}\)\s\d{3}\-\d{4}"
        after_phone = False

        for line in address_lines:
            if re.search(r"(?i)open\s+\w+day", address_lines[0]):
                continue
            elif "FAX" in line:
                fax = line.replace("FAX ", "")
                after_phone = True
            elif re.search(PHONE_RE, line):
                phone = line
                after_phone = True
            elif not after_phone:
                clean_address_lines.append(line)

        address = "\n".join(clean_address_lines)
        address = re.sub(r"\s{2,}", " ", address)
        obj_office.address = address
        obj_office.phone = phone
        obj_office.fax = fax


class SenList(ListPage):
    url = "http://www.flsenate.gov/Senators/"
    list_xpath = "//a[@class='senatorLink']"
    detail_pages = [SenDetail, SenContactDetail]

    def handle_list_item(self, item):
        name = " ".join(item.xpath(".//text()"))
        name = re.sub(r"\s+", " ", name).replace(" ,", ",").strip()

        if "Vacant" in name:
            return

        district = item.xpath("string(../../td[1])")
        party = item.xpath("string(../../td[2])")
        leg_url = item.get("href")

        name = fix_name(name)
        leg = Person(
            name=str(name), state="fl", party=str(party), district=str(district), chamber="upper",
        )
        leg.add_link(leg_url)
        leg.add_source(self.url)
        leg.add_source(leg_url)

        return leg


class RepContact(Page):
    def get_url(self):
        """
        Transform from
            /Sections/Representatives/details.aspx?MemberId=4640&LegislativeTermId=88
        to:
            /Sections/Representatives/contactmember.aspx?MemberId=4737&SessionId=89
        """
        details_url = self.obj.links[0]["url"]
        contact_url = details_url.replace("details.aspx", "contactmember.aspx")
        return contact_url

    def handle_page(self):
        for otype in ("district", "capitol"):
            odoc = self.doc.xpath(f"//h3[@id='{otype}-office']/following-sibling::ul")
            if odoc:
                odoc = odoc[0]
            else:
                continue
            spans = odoc.xpath(".//span")

            office = self.obj.capitol_office if otype == "capitol" else self.obj.district_office
            office.address = "; ".join(
                line.strip()
                for line in spans[0].text_content().strip().splitlines()
                if line.strip()
            )
            office.voice = spans[1].text_content().strip()


class RepList(ListPage):
    url = "https://www.myfloridahouse.gov/Representatives"
    list_xpath = "//div[@class='team-box']"
    detail_pages = [RepContact]

    IMAGE_BASE = "https://www.myfloridahouse.gov/"

    def handle_list_item(self, item):
        name = item.xpath("./a/div[@class='team-txt']/h5/text()")[0].strip()
        party = item.xpath("./a/div[@class='team-txt']/p[1]/text()")[0].split()[0]
        district = item.xpath("./a/div[@class='team-txt']/p[1]/span/text()")[0].split()[-1]
        image = self.IMAGE_BASE + item.xpath(".//img")[0].attrib["data-src"]
        link = str(item.xpath("./a/@href")[0])

        rep = Person(
            name=fix_name(name),
            state="fl",
            party=str(party),
            district=str(district),
            chamber="lower",
            image=image,
        )
        rep.add_link(link)
        rep.add_source(self.url)
        rep.add_source(link)
        return rep


# import tempfile
# from pupa.utils import convert_pdf

#     directory_pdf_url = (
#         "http://www.myfloridahouse.gov/FileStores/Web/"
#         "HouseContent/Approved/ClerksOffice/HouseDirectory.pdf"
#     )

#     def _load_emails_from_directory_pdf(self):
#         """
#         Load the house PDF directory and convert to LXML - needed to
#         find email addresses which are gone from the website.
#         """
#         with tempfile.NamedTemporaryFile() as temp:
#             self.scraper.urlretrieve(self.directory_pdf_url, temp.name)
#             directory = lxml.etree.fromstring(convert_pdf(temp.name, "xml"))

#         # pull out member email addresses from the XML salad produced
#         # above - there's no obvious way to match these to names, but
#         # fortunately they have names in them
#         return set(
#             directory.xpath('//text[contains(text(), "@myfloridahouse.gov")]/text()')
#         )

#     def handle_list_item(self, item):
#         # look for email in the list from the PDF directory - ideally
#         # we'd find a way to better index the source data which
#         # wouldn't require guessing the email, but this does at least
#         # confirm that it's correct

#         # deal with some stuff that ends up in name that won't work in
#         # email, spaces, quotes, high latin1
#         email_name = rep.name.replace('"', "").replace("La ", "La").replace("ñ", "n")
#         (last, *other) = re.split(r"[-\s,]+", email_name)

#         # deal with a missing nickname used in an email address
#         if "Patricia" in other:
#             other.append("Pat")

#         # search through all possible first names and nicknames
#         # present - needed for some of the more elaborate concoctions
#         found_email = False
#         for first in other:
#             email = "%s.%s@myfloridahouse.gov" % (first, last)
#             if email in self.member_emails:
#                 # it's bad if we can't uniquely match emails, so throw an error
#                 if email in self.claimed_member_emails:
#                     raise ValueError(
#                         "Email address %s matches multiple reps - %s and %s."
#                         % (email, rep.name, self.claimed_member_emails[email])
#                     )

#                 self.claimed_member_emails[email] = rep.name

#                 rep.add_contact_detail(type="email", value=email, note="Capitol Office")
#                 rep.add_source(self.directory_pdf_url)

#                 found_email = True

#                 break

#         if not found_email:
#             log.warning(
#                 "Rep %s does not have an email in the directory PDF." % (rep.name,)
#             )

#         return rep


def main():
    try:
        os.makedirs("incoming/fl/people")
    except OSError:
        pass
    sen = SenList()
    for leg in sen.handle_page():
        leg.save("incoming/fl/people")
    rep = RepList()
    for leg in rep.handle_page():
        leg.save("incoming/fl/people")


if __name__ == "__main__":
    main()
