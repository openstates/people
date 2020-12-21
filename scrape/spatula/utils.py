import re
import scrapelib
import lxml.html


def elem_to_str(item, inside=False):
    attribs = "  ".join(f"{k}='{v}'" for k, v in item.attrib.items())
    return f"<{item.tag} {attribs}> @ line {item.sourceline}"


class Selector:
    def __init__(self, *, min_items=1, max_items=None, num_items=None):
        self.min_items = min_items
        self.max_items = max_items
        self.num_items = num_items

    def match(self, element, *, min_items=None, max_items=None, num_items=None):
        items = list(self.get_items(element))
        num_items = self.num_items if num_items is None else num_items
        max_items = self.max_items if max_items is None else max_items
        min_items = self.min_items if min_items is None else min_items

        if num_items is not None and len(items) != num_items:
            raise XPathError(
                f"{self.get_display()} on {elem_to_str(element)} got {len(items)}, "
                f"expected {num_items}"
            )
        if min_items is not None and len(items) < min_items:
            raise XPathError(
                f"{self.get_display()} on {elem_to_str(element)} got {len(items)}, "
                f"expected at least {min_items}"
            )
        if max_items is not None and len(items) > max_items:
            raise XPathError(
                f"{self.get_display()} on {elem_to_str(element)} got {len(items)}, "
                f"expected at most {max_items}"
            )

        return items

    def match_one(self, element):
        return str(self.match(element, num_items=1)[0])


class XPath(Selector):
    def __init__(self, xpath, *, min_items=1, max_items=None, num_items=None):
        super().__init__(min_items=min_items, max_items=max_items, num_items=num_items)
        self.xpath = xpath

    def get_items(self, element):
        yield from element.xpath(self.xpath)

    def get_display(self):
        return f"XPath({self.xpath})"


class SimilarLink(Selector):
    def __init__(self, pattern, *, min_items=1, max_items=None, num_items=None):
        super().__init__(min_items=min_items, max_items=max_items, num_items=num_items)
        self.pattern = re.compile(pattern)

    def get_items(self, element):
        for element in element.xpath("//a"):
            if self.pattern.match(element.get("href", "")):
                yield element

    def get_display(self):
        return f"SimilarLink({self.pattern})"


class NoSuchScraper(Exception):
    pass


class XPathError(ValueError):
    pass


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
        """
        converts intermediate data (often in a dictionary) to a final object to be validated
        """
        return item

    def start_scrape(self, chamber, session):
        """
        yields one or more Page objects that will kick off the scrape.

        It may also raise a ValueError (TBD) when it does not have an appropriate entrypoint
        to scrape the requested data.
        """
        raise NotImplementedError()


class Page:
    def __init__(self, url):
        """
        a Page can be instantiated with a url & options (TBD) needed to fetch it
        """
        self.url = url

    def set_raw_data(self, raw_data):
        """ callback to handle raw data returned by grabbing the URL """
        self.raw_data = raw_data

    def get_data(self):
        """ return data extracted from this page and this page alone """
        raise NotImplementedError()


class HtmlPage(Page):
    def set_raw_data(self, raw_data):
        super().set_raw_data(raw_data)
        self.root = lxml.html.fromstring(raw_data.content)
        self.root.make_links_absolute(self.url)


class HtmlListPage(HtmlPage):
    """
    Simplification for HTML pages that get a list of items and process them.

    When overriding the class, instead of providing get_data, one must only provide
    a selector and a process_item function.
    """

    selector = None

    def get_data(self):
        if not self.selector:
            raise NotImplementedError("must either provide selector or override scrape")
        items = self.selector.match(self.root)
        for item in items:
            item = self.process_item(item)
            yield item

    def process_item(self, item):
        return item
