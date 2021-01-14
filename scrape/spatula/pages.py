import json
import lxml.html
from .core import URL


class Page:
    source = None
    dependencies = {}

    def _fetch_data(self, scraper):
        # process dependencies first
        for val, dep in self.dependencies.items():
            dep._fetch_data(scraper)
            setattr(self, val, dep.get_data())

        if not self.source:
            if hasattr(self, "get_source_from_input"):
                self.source = self.get_source_from_input()
            else:
                raise Exception(
                    f"{self.__class__.__name__} has no source or get_source_from_input"
                )
        if isinstance(self.source, str):
            self.source = URL(self.source)
        print(f"fetching {self.source} for {self.__class__.__name__}")
        data = self.source.get_data(scraper)
        self.set_raw_data(data)

    def __init__(self, input_val=None, *, source=None):
        """
        a Page can be instantiated with a url & options (TBD) needed to fetch it
        """
        self.input = input_val
        # possibly override existing source, useful during dev
        if source:
            self.source = source
        # TODO: restore special case? maybe __url__ or something?
        # if isinstance(input_val, dict) and "url" in input_val:
        #     self.source = URL(input_val["url"])
        # if hasattr(input_val, "url"):
        #     self.source = URL(input_val.url)

    def set_raw_data(self, raw_data):
        """ callback to handle raw data returned by grabbing the URL """
        self.raw_data = raw_data

    def get_data(self):
        """ return data extracted from this page and this page alone """
        raise NotImplementedError()


class HtmlPage(Page):
    def set_raw_data(self, raw_data):
        super().set_raw_data(raw_data)
        self.root = lxml.html.fromstring(raw_data)
        if hasattr(self.source, "url"):
            self.root.make_links_absolute(self.source.url)


class XmlPage(Page):
    def set_raw_data(self, raw_data):
        super().set_raw_data(raw_data)
        self.root = lxml.etree.fromstring(raw_data)


class JsonPage(Page):
    def set_raw_data(self, raw_data):
        super().set_raw_data(raw_data)
        self.data = json.loads(raw_data)


class ListPage(Page):
    class SkipItem(Exception):
        pass

    def skip(self):
        raise self.SkipItem()

    def process_item(self, item):
        return item


# TODO
# class CSVListPage(ListPage):
#     def get_data(self):
#         print(self.raw_data)
#         for item in items:
#             try:
#                 item = self.process_item(item)
#             except self.SkipItem:
#                 continue
#             yield item

#     def process_item(self, item):
#         return item


class LxmlListPage(ListPage):
    """
    Base class for XML and HTML subclasses below, only difference is which parser is used.

    Simplification for pages that get a list of items and process them.

    When overriding the class, instead of providing get_data, one must only provide
    a selector and a process_item function.
    """

    selector = None

    def get_data(self):
        if not self.selector:
            raise NotImplementedError("must either provide selector or override scrape")
        items = self.selector.match(self.root)
        for item in items:
            try:
                item = self.process_item(item)
            except self.SkipItem:
                continue
            yield item


class HtmlListPage(LxmlListPage, HtmlPage):
    pass


class XmlListPage(LxmlListPage, XmlPage):
    pass


class JsonListPage(ListPage, JsonPage):
    def get_data(self):
        for item in self.data:
            try:
                item = self.process_item(item)
            except self.SkipItem:
                continue
            yield item
