import os
import glob
import datetime
import scrapelib
from utils import dump_obj


class Workflow:
    def __init__(self, initial_page, page_processor_cls=None, scraper=None):
        self.initial_page = initial_page
        self.page_processor_cls = page_processor_cls
        if not scraper:
            self.scraper = scrapelib.Scraper()

    def execute(self, output_dir=None):
        count = 0
        if not output_dir:
            dirn = 1
            today = datetime.date.today().strftime("%Y-%m-%d")
            while True:
                try:
                    output_dir = f"_scrapes/{today}/{dirn:03d}"
                    os.makedirs(output_dir)
                    break
                except FileExistsError:
                    dirn += 1
        else:
            try:
                os.makedirs(output_dir)
            except FileExistsError:
                if len(glob.glob(output_dir + "/*")):
                    raise FileExistsError(f"{output_dir} exists and is not empty")

        self.initial_page._fetch_data(self.scraper)
        for i, item in enumerate(self.initial_page.get_data()):
            if self.page_processor_cls:
                page = self.page_processor_cls(item)
                page._fetch_data(self.scraper)
                data = page.get_data()
            else:
                data = item
            count += 1
            dump_obj(data.to_dict(), output_dir=output_dir)
        print(f"success: wrote {count} objects to {output_dir}")


class Source:
    pass


class URL(Source):
    def __init__(self, url, method="GET", data=None, headers=None):
        self.url = url
        self.method = method
        self.data = data
        self.headers = headers

    def get_data(self, scraper):
        return scraper.request(
            method=self.method, url=self.url, data=self.data, headers=self.headers
        ).content

    def __str__(self):
        return self.url


class NullSource(Source):
    def get_data(self, scraper):
        return None

    def __str__(self):
        return self.__class__.__name__
