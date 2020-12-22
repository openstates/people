from spatula.utils import HtmlListPage, SimilarLink, HtmlPage, CSS


class OKSenateList(HtmlListPage):
    selector = SimilarLink("https://oksenate.gov/senators/", num_items=48)
    url = "https://oksenate.gov/senators"

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
    url = "https://www.okhouse.gov/Members/Default.aspx"

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

        contact_url = self.url.replace("District.aspx", "Contact.aspx")
        assert contact_url.startswith("https://www.okhouse.gov/Members/Contact.aspx?District=")
        data["contact_url"] = contact_url

        # capitol address
        check_capitol_address = CSS(".districtheadleft").match(self.root)[0].text_content().strip()
        if check_capitol_address == "Capitol Address:":
            capitol_address_div = (
                CSS(".districtheadleft + div")
                .match(self.root)[0]
                .text_content()
                .strip()
                .splitlines()
            )
            data["address"] = "; ".join([ln.strip() for ln in capitol_address_div[:-1]])
            data["phone"] = capitol_address_div[-1].strip()
        return data


class OKSenateDetail(HtmlPage):
    name_css = CSS(".field--name-title")
    image_css = CSS(".bSenBio__media-btn")
    district_css = CSS(".bDistrict h2")
    address_css = CSS(".bSenBio__address p")
    phone_css = CSS(".bSenBio__tel a")
    contact_link_sel = SimilarLink(r"https://oksenate.gov/contact-senator\?sid=")

    def get_data(self):
        data = {
            "name": self.name_css.match_one(self.root).text,
            "image": self.image_css.match_one(self.root).get("href"),
            "district": self.district_css.match_one(self.root).text.strip().split()[1],
            "address": self.address_css.match_one(self.root).text,
            "phone": self.phone_css.match_one(self.root).text,
            "contact_url": self.contact_link_sel.match_one(self.root).get("href"),
        }

        for bio in CSS(".bSenBio__infoIt").match(self.root):
            if "Party:" in bio.text_content():
                data["party"] = bio.text_content().split(":")[1].strip()
        return data
