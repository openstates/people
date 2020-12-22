import os
import scrapelib
from utils import dump_obj


class Scraper(scrapelib.Scraper):
    def fetch_page_data(self, page):
        print(f"fetching {page.url} for {page.__class__.__name__}")
        data = self.get(page.url)
        page.set_raw_data(data)


class Workflow:
    def __init__(self, initial_page, page_processor_cls, scraper=None):
        self.initial_page = initial_page
        self.page_processor_cls = page_processor_cls
        if not scraper:
            self.scraper = Scraper()

    def execute(self):
        directory = "_data"
        os.makedirs(directory, exist_ok=True)
        self.scraper.fetch_page_data(self.initial_page)

        for i, item in enumerate(self.initial_page.get_data()):
            # print(f"{i}:", _display(item))
            page = self.page_processor_cls(item["url"])
            self.scraper.fetch_page_data(page)
            data = page.get_data()
            dump_obj(data.to_dict(), output_dir=directory)
