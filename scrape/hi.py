import lxml.html

# from spatula.core import Workflow
from spatula.pages import HtmlListPage
from spatula.selectors import CSS, SelectorError

# from common import Person


class FormSource:
    def __init__(self, url, form_xpath, button_label):
        self.url = url
        self.form_xpath = form_xpath
        self.button_label = button_label

    def get_data(self, scraper):
        resp = scraper.get(self.url)
        root = lxml.html.fromstring(resp.content)
        form = root.xpath(self.form_xpath)[0]
        inputs = form.xpath(".//input")
        # build list of all of the inputs of the form, clicking the button we need to click
        data = {}
        for inp in inputs:
            name = inp.get("name")
            value = inp.get("value")
            inptype = inp.get("type")
            if inptype == "submit":
                if value == self.button_label:
                    data[name] = value
            else:
                data[name] = value

        # do second request
        resp = scraper.post(self.url, data)
        return resp.content


class HawaiiLegislators(HtmlListPage):
    source = FormSource(
        "https://www.capitol.hawaii.gov/members/legislators.aspx", "//form", "Show All"
    )
    selector = CSS("#ctl00_ContentPlaceHolderCol1_GridView1 tr")

    def process_item(self, item):
        try:
            link = CSS("a").match(item)[1]
        except SelectorError:
            self.skip()
        return {
            "name": link.text_content(),
            "url": link.get("href"),
        }
