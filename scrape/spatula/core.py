import os
import glob
import datetime
import scrapelib
from utils import dump_obj


class Scraper(scrapelib.Scraper):
    def fetch_page_data(self, page):
        if not hasattr(page, "source"):
            if hasattr(page, "get_source_from_input"):
                page.source = page.get_source_from_input()
            else:
                raise Exception(
                    f"{page.__class__.__name__} has no source or get_source_from_input"
                )
        print(f"fetching {page.source} for {page.__class__.__name__}")
        data = page.source.get_data(self)
        page.set_raw_data(data)


class Workflow:
    def __init__(self, initial_page, page_processor_cls=None, scraper=None):
        self.initial_page = initial_page
        self.page_processor_cls = page_processor_cls
        if not scraper:
            self.scraper = Scraper()

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

        self.scraper.fetch_page_data(self.initial_page)

        for i, item in enumerate(self.initial_page.get_data()):
            if self.page_processor_cls:
                page = self.page_processor_cls(item)
                self.scraper.fetch_page_data(page)
                data = page.get_data()
            else:
                data = item
            count += 1
            dump_obj(data.to_dict(), output_dir=output_dir)
        print(f"success: wrote {count} objects to {output_dir}")
