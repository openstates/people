from spatula.utils import HtmlListPage, SimilarLink, HtmlPage, CSS


class OKSenateList(HtmlListPage):
    selector = SimilarLink("https://oksenate.gov/senators/", num_items=48)

    def __init__(self):
        super().__init__(url="https://oksenate.gov/senators")

    def process_item(self, item):
        party, _, district, name = item.text_content().split(maxsplit=3)
        return {
            "url": item.get("href"),
            "party": party,
            "district": district,
            "name": name.strip(),
        }


class OKHouseList(HtmlListPage):
    selector = SimilarLink(
        r"https://www.okhouse.gov/Members/District.aspx\?District=", num_items=101
    )

    def __init__(self):
        super().__init__(url="https://www.okhouse.gov/Members/Default.aspx")

    def process_item(self, item):
        return {
            "url": item.get("href"),
            "name": item.text.strip(),
        }


class OKHouseDetail(HtmlPage):

    image_selector = SimilarLink("https://www.okhouse.gov/Members/Pictures/HiRes/")
    prefix = "#ctl00_ContentPlaceHolder1_lbl"
    name_css = CSS(prefix + "Name")
    district_css = CSS(prefix + "District")
    party_css = CSS(prefix + "Party")

    def get_data(self):
        data = {}
        data["image"] = self.image_selector.match_one(self.root).get("href")
        data["name"] = self.name_css.match_one(self.root).text.split(maxsplit=1)[1]
        data["district"] = self.district_css.match_one(self.root).text
        data["party"] = self.party_css.match_one(self.root).text
        return data
