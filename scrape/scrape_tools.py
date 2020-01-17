import scrapelib
import lxml.html


class BaseScraper(scrapelib.Scraper):
    def __init__(self):
        super().__init__()
        self.parent = None

    def lxml(self, url):
        print(f"fetching {url} for {self.__class__.__name__}")
        html = self.get(url)
        doc = lxml.html.fromstring(html.content)
        doc.make_links_absolute(url)
        return doc


class ListScraper(BaseScraper):
    def run(self):
        self.doc = self.lxml(self.url)

        items = self.doc.xpath(self.list_xpath)
        if not items:
            raise ValueError(f"no items for {self.list_xpath} on {self.url}")
        for item in items:
            obj = self.handle_list_item(item)
            if obj:
                for PageCls in self.detail_pages:
                    page = PageCls(obj)
                    page.fetch(using=self)
                    page.handle_page()
                yield obj


class DetailPage(BaseScraper):
    """
    This class augments an object with additional details.
    """

    def __init__(self, obj, url=None):
        super().__init__()
        self.obj = obj
        self.url = url

    def fetch(self, *, using=None):
        if not self.url:
            self.url = self.get_url()
        if not using:
            using = self
        self.doc = using.lxml(self.url)
