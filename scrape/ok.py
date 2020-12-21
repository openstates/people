from spatula.utils import HtmlListPage, SimilarLink


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
        }
