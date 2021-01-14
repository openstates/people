import lxml.html
from .core import URL


class Page:
    source = None
    dependencies = {}

    def _fetch_data(self, scraper):
        """
        ensure that the page has all of its data, this is guaranteed to be called exactly once
        before get_data is invoked
        """
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
        self.response = self.source.get_response(scraper)
        self.postprocess_response()

    def __init__(self, input_val=None, *, source=None):
        self.input = input_val
        # allow possibility to override default source, useful during dev
        if source:
            self.source = source

    def postprocess_response(self):
        """ this is called after source.get_response but before self.process_page """
        pass

    def get_data(self):
        """ return data extracted from this page and this page alone """
        raise NotImplementedError()


class HtmlPage(Page):
    def postprocess_response(self):
        self.root = lxml.html.fromstring(self.response.content)
        if hasattr(self.source, "url"):
            self.root.make_links_absolute(self.source.url)


class XmlPage(Page):
    def postprocess_response(self):
        self.root = lxml.etree.fromstring(self.response.content)


class JsonPage(Page):
    def postprocess_response(self):
        self.data = self.response.json()


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
