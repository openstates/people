import scrapelib
import lxml.html
from functools import lru_cache


class NoSuchScraper(Exception):
    pass


class XPathError(ValueError):
    pass


class BaseScraper(scrapelib.Scraper):
    root_xpath = None
    url = None

    @lru_cache(maxsize=None)
    def lxml(self, url):
        """
        method that actually fetches the data, might be called by a child class
        """
        print(f"fetching {url} via {self.__class__.__name__}")
        html = self.get(url)
        doc = lxml.html.fromstring(html.content)
        doc.make_links_absolute(url)
        return doc

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def yield_root_objects(self):
        if not self.root_xpath:
            raise NotImplementedError(
                "must either provide root_xpath or override yield_root_objects"
            )
        items = self.root_xpath.match(self.doc)
        for item in items:
            yield self.process_root_item(item)

    def process_root_item(self, item):
        return item


def elem_to_str(item, inside=False):
    attribs = "  ".join(f"{k}='{v}'" for k, v in item.attrib.items())
    return f"<{item.tag} {attribs}> @ line {item.sourceline}"


class XPath:
    def __init__(self, xpath, min_items=1, max_items=None, num_items=None):
        self.xpath = xpath
        self.min_items = min_items
        self.max_items = max_items
        self.num_items = num_items

    def match(self, element, *, num_items=None):
        items = element.xpath(self.xpath)

        num_items = self.num_items if num_items is None else num_items

        if num_items is not None and len(items) != num_items:
            print(items)
            raise XPathError(
                f"{self.xpath} on {elem_to_str(element)} got {len(items)}, "
                f"expected {num_items}"
            )
        if self.min_items is not None and len(items) < self.min_items:
            raise XPathError(
                f"{self.xpath} on {elem_to_str(element)} got {len(items)}, "
                f"expected at least {self.min_items}"
            )
        if self.max_items is not None and len(items) > self.max_items:
            raise XPathError(
                f"{self.xpath} on {elem_to_str(element)} got {len(items)}, "
                f"expected at most {self.max_items}"
            )

        return items

    def match_one(self, element):
        return self.match(element, num_items=1)[0]


class MDPersonScraper(BaseScraper):
    root_xpath = XPath("//div[@id='myDIV']//div[@class='p-0 member-index-cell']")

    def __init__(self, url, **kwargs):
        super().__init__(**kwargs)
        self.url = url
        self.doc = self.lxml(self.url)

    def process_root_item(self, item):
        dd_text = XPath(".//dd/text()").match(item)
        district = dd_text[2].strip()
        party = dd_text[4].strip()
        return {
            "img": XPath(".//img/@src").match_one(item),
            "name": XPath(".//dd/a[1]/text()").match_one(item),
            "link": XPath(".//dd/a[1]/@href").match_one(item),
            "district": district,
            "party": party,
        }


def parameter_dispatch(chamber, session=None):
    """
    this function converts accepted parameters to an instance of a class
    that can do the scraping
    """
    if session:
        raise NoSuchScraper("cannot scrape non-current sessions")
    if chamber == "upper":
        scraper = MDPersonScraper("http://mgaleg.maryland.gov/mgawebsite/Members/Index/senate")
    elif chamber == "lower":
        scraper = MDPersonScraper("http://mgaleg.maryland.gov/mgawebsite/Members/Index/house")

    for partial_obj in scraper.yield_root_objects():
        print(partial_obj)


parameter_dispatch("upper")
