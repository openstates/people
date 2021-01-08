from spatula.pages import HtmlListPage, HtmlPage
from spatula.sources import URL
from spatula.selectors import CSS, SelectorError
from common import Person


class PartyAugmentation(HtmlPage):
    """
    NY Assembly does not have partisan information on their site.

    In the past we scraped NYBOE, but that broke.  This is our best option
    besides hard-coding... and it isn't good.
    """

    source = URL("https://en.wikipedia.org/wiki/New_York_State_Assembly")

    def find_rows(self):
        # the first table on the page that has a bunch of rows
        for table in CSS("table.wikitable").match(self.root):
            rows = CSS("tr").match(table)
            if len(rows) >= 150:
                return rows

    def get_data(self):
        mapping = {}
        rows = self.find_rows()
        for row in rows:
            tds = row.getchildren()
            dist = tds[0].text_content().strip()
            name = tds[1].text_content().strip()
            party = tds[2].text_content().strip()
            mapping[dist] = (name, party)
        return mapping


class AssemblyList(HtmlListPage):
    source = URL("https://assembly.state.ny.us/mem/")
    selector = CSS("section.mem-item", num_items=150)
    dependencies = {"party_mapping": PartyAugmentation()}

    def process_item(self, item):
        # strip leading zero
        district = str(int(item.get("id")))
        image = CSS(".mem-pic a img").match_one(item).get("src")
        name = CSS(".mem-name a").match_one(item)

        # email, twitter, facebook are all sometimes present
        try:
            email = CSS(".mem-email a").match_one(item).text.strip()
        except SelectorError:
            email = ""
        try:
            twitter = CSS(".fa-twitter").match_one(item)
            twitter = twitter.getparent().get("href").split("/")[-1]
        except SelectorError:
            twitter = ""
        try:
            facebook = CSS(".fa-facebook").match_one(item)
            facebook = facebook.getparent().get("href").split("/")[-1]
        except SelectorError:
            facebook = ""

        party = self.party_mapping[district][1]

        p = Person(
            state="ny",
            chamber="lower",
            image=image,
            party=party,
            district=district,
            name=name.text.strip(),
            email=email,
        )
        p.add_link(url=name.get("href"))
        p.add_source(url=name.get("href"))
        if twitter:
            p.ids["twitter"] = twitter
        if facebook:
            p.ids["facebook"] = facebook
        return p
