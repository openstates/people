import re
from common import Person
from spatula import HtmlPage, HtmlListPage, XPath, Scraper, NoSuchScraper

# @attr.s
# class ContactDetail:
#     note = attr.ib()
#     voice = attr.ib()
#     email =attr.ib()
#     fax = attr.ib()
#     address = attr.ib()


# @attr.s
# class Person:
#     name = attr.ib()
#     state = attr.ib()
#     party = attr.ib()
#     district = attr.ib()
#     chamber = attr.ib()
#     image = attr.ib(default=None)
#     given_name = attr.ib(default=None)
#     family_name = attr.ib(default=None)
#     links = attr.ib(default=attr.Factory(list))
#     sources = attr.ib(default=attr.Factory(list))
#     capitol_office = attr.ib(default=None)
#     district_office = attr.ib(default=None)


class MDPersonDetail(HtmlPage):
    def __init__(self, url):
        self.url = url

    def parse_address_block(self, block):
        state = "address"
        # group lines by type
        values = {"address": [], "phone": [], "fax": []}
        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("Phone"):
                state = "phone"
            elif line.startswith("Fax"):
                state = "fax"

            values[state].append(line)

        # postprocess values

        phones = []
        for line in values["phone"]:
            for match in re.findall(r"\d{3}-\d{3}-\d{4}", line):
                phones.append(match)

        faxes = []
        for line in values["fax"]:
            for match in re.findall(r"\d{3}-\d{3}-\d{4}", line):
                faxes.append(match)

        return {"address": "; ".join(values["address"]), "phones": phones, "faxes": faxes}

    def get_data(self):
        # annapolis_info = (
        #     XPath("//dt[text()='Annapolis Info']/following-sibling::dd[1]")
        #     .match_one(self.root)
        #     .text_content()
        # )
        # interim_info = (
        #     XPath("//dt[text()='Interim Info']/following-sibling::dd[1]")
        #     .match_one(self.root)
        #     .text_content()
        # )
        # print(self.parse_address_block(annapolis_info))
        # print(self.parse_address_block(interim_info))

        return dict(
            name=XPath("//h2/text()").match_one(self.root).split(" ", 1)[1],
            # "email": XPath(
            #     "//dt[text()='Contact']/following-sibling::dd[1]/a[1]/text()"
            # ).match_one(self.root),
        )


class MDPersonList(HtmlListPage):
    xpath = XPath("//div[@id='myDIV']//div[@class='p-0 member-index-cell']")
    subpages = [lambda item: MDPersonDetail(item["link"])]

    def __init__(self, url):
        self.url = url

    def process_item(self, item):
        dd_text = XPath(".//dd/text()").match(item)
        district = dd_text[2].strip().split()[1]
        party = dd_text[4].strip()
        return dict(
            chamber="upper" if "senate" in self.url else "lower",
            image=XPath(".//img/@src").match_one(item),
            district=district,
            party=party,
            link=XPath(".//dd/a[1]/@href").match_one(item),
        )


class MDPersonScraper(Scraper):
    def start_scrape(self, chamber, session):
        """ This function yields one or more Page objects that will kick off the scrape.

        It may also raise a ValueError (TBD) when it does not have an appropriate entrypoint
        to scrape the requested data.
        """

        if session:
            raise NoSuchScraper("cannot scrape non-current sessions")
        if chamber == "upper":
            yield MDPersonList("http://mgaleg.maryland.gov/mgawebsite/Members/Index/senate")
        elif chamber == "lower":
            yield MDPersonList("http://mgaleg.maryland.gov/mgawebsite/Members/Index/house")

    def to_object(self, item):
        p = Person(
            state="md",
            chamber=item["chamber"],
            name=item["name"],
            party=item["party"],
            image=item["image"],
            district=item["district"],
        )
        p.add_link(item["link"])
        p.add_source(item["link"])
        return p
