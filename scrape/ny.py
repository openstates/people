from spatula.pages import HtmlListPage, HtmlPage
from spatula.sources import URL
from spatula.selectors import CSS, SelectorError
from common import Person


class PartyAugmentationData(HtmlPage):
    """
    NY Assembly does not have partisan information on their site.

    In the past we scraped NYBOE, but that broke.  This is our best option
    besides hard-coding... and it isn't good.
    """


class AssemblyList(HtmlListPage):
    source = URL("https://assembly.state.ny.us/mem/")
    selector = CSS("section.mem-item", num_items=150)

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
            twitter = twitter.getparent().get("href")
        except SelectorError:
            twitter = ""
        try:
            facebook = CSS(".fa-facebook").match_one(item)
            facebook = facebook.getparent().get("href")
        except SelectorError:
            facebook = ""

        p = Person(
            state="ny",
            chamber="lower",
            image=image,
            district=district,
            name=name.text.strip(),
            email=email,
            party="Unknown",
        )
        p.add_link(url=name.get("href"))
        p.add_source(url=name.get("href"))
        p.twitter = twitter
        p.facebook = facebook
        return p
