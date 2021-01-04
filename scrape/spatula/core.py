import os
import datetime
import scrapelib
from utils import dump_obj


class Source:
    pass


class URL(Source):
    def __init__(self, url):
        self.url = url

    def get_data(self, scraper):
        return scraper.get(self.url).content

    def __str__(self):
        return self.url


class Scraper(scrapelib.Scraper):
    def fetch_page_data(self, page):
        # allow simple scrapers to use X.url instead of X.source
        if hasattr(page, "url"):
            source = URL(page.url)
        else:
            source = page.source
        print(f"fetching {source} for {page.__class__.__name__}")
        data = source.get_data(self)
        page.set_raw_data(data)


class Workflow:
    def __init__(self, initial_page, page_processor_cls=None, scraper=None):
        self.initial_page = initial_page
        self.page_processor_cls = page_processor_cls
        if not scraper:
            self.scraper = Scraper()

    def execute(self):
        count = 0
        dirn = 1
        today = datetime.date.today().strftime("%Y-%m-%d")
        while True:
            try:
                directory = f"_scrapes/{today}/{dirn:03d}"
                os.makedirs(directory)
                break
            except FileExistsError:
                dirn += 1
        self.scraper.fetch_page_data(self.initial_page)

        for i, item in enumerate(self.initial_page.get_data()):
            if self.page_processor_cls:
                page = self.page_processor_cls(item["url"])
                self.scraper.fetch_page_data(page)
                data = page.get_data()
            else:
                data = item
            count += 1
            dump_obj(data.to_dict(), output_dir=directory)
        print(f"success: wrote {count} objects to {directory}")
