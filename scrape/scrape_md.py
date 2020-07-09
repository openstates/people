import re
import lxml.html
import click
import scrapelib


def elem_to_str(item, inside=False):
    attribs = "  ".join(f"{k}='{v}'" for k, v in item.attrib.items())
    return f"<{item.tag} {attribs}> @ line {item.sourceline}"


class XPath:
    def __init__(self, xpath, *, min_items=1, max_items=None, num_items=None):
        self.xpath = xpath
        self.min_items = min_items
        self.max_items = max_items
        self.num_items = num_items

    def match(self, element, *, min_items=None, max_items=None, num_items=None):
        items = element.xpath(self.xpath)

        num_items = self.num_items if num_items is None else num_items
        max_items = self.max_items if max_items is None else max_items
        min_items = self.min_items if min_items is None else min_items

        if num_items is not None and len(items) != num_items:
            print(items)
            raise XPathError(
                f"{self.xpath} on {elem_to_str(element)} got {len(items)}, "
                f"expected {num_items}"
            )
        if min_items is not None and len(items) < min_items:
            raise XPathError(
                f"{self.xpath} on {elem_to_str(element)} got {len(items)}, "
                f"expected at least {min_items}"
            )
        if max_items is not None and len(items) > max_items:
            raise XPathError(
                f"{self.xpath} on {elem_to_str(element)} got {len(items)}, "
                f"expected at most {max_items}"
            )

        return items

    def match_one(self, element):
        return self.match(element, num_items=1)[0]


class NoSuchScraper(Exception):
    pass


class XPathError(ValueError):
    pass


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


class Scraper(scrapelib.Scraper):
    def fetch_page_data(self, page):
        print(f"fetching {page.url} for {page.__class__.__name__}")
        data = self.get(page.url)
        page.set_raw_data(data)

    def augment_item(self, item, subpages):
        for subpage_func in subpages:
            page = subpage_func(item)
            self.fetch_page_data(page)
            page_data = page.get_data()
            item.update(page_data)
            return item

    def scrape(self, chamber, session):
        for page in self.start_scrape(chamber, session):
            self.fetch_page_data(page)
            for item in page.get_data():
                if page.subpages:
                    item = self.augment_item(item, page.subpages)
                if isinstance(item, dict):
                    item = self.to_object(item)
                yield item

    def to_object(self, item):
        return item


class HtmlPage:
    def __init__(self, url):
        self.url = url

    def set_raw_data(self, raw_data):
        self.raw_data = raw_data
        self.root = lxml.html.fromstring(raw_data.content)
        self.root.make_links_absolute(self.url)

    def get_data(self):
        pass


class HtmlListPage(HtmlPage):
    xpath = None

    def get_data(self):
        if not self.xpath:
            raise NotImplementedError("must either provide xpath or override scrape")
        items = self.xpath.match(self.root)
        for item in items:
            item = self.process_item(item)
            yield item

    def process_item(self, item):
        return item


class MDPersonDetail(HtmlPage):
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

    def process_item(self, item):
        dd_text = XPath(".//dd/text()").match(item)
        district = dd_text[2].strip()
        party = dd_text[4].strip()
        return dict(
            image=XPath(".//img/@src").match_one(item),
            district=district,
            party=party,
            link=XPath(".//dd/a[1]/@href").match_one(item),
        )


class MDPersonScraper(Scraper):
    def start_scrape(self, chamber, session):
        if session:
            raise NoSuchScraper("cannot scrape non-current sessions")
        if chamber == "upper":
            yield MDPersonList("http://mgaleg.maryland.gov/mgawebsite/Members/Index/senate")
        elif chamber == "lower":
            yield MDPersonList("http://mgaleg.maryland.gov/mgawebsite/Members/Index/house")

    def to_object(self, item):
        return item


@click.group()
def cli():
    pass


@cli.command()
@click.argument("class_name")
@click.argument("url")
def sample(class_name, url):
    # implementation is a stub, this will be able to accept dotted paths once implemented
    Cls = globals()[class_name]
    page = Cls(url)
    s = Scraper()
    s.fetch_page_data(page)
    print(page.get_data())


@cli.command()
@click.option("--chamber", multiple=True, default=["upper", "lower"])
@click.option("--session", default=None)
def scrape(chamber, session):
    for ch in chamber:
        for item in MDPersonScraper().scrape(ch, session):
            print(item)


if __name__ == "__main__":
    cli()
