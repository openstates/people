import io
import csv
import attr
import lxml.html
from spatula import HtmlPage, URL, CSS, CsvListPage
from .common.people import Person, PeopleWorkflow


@attr.s(auto_attribs=True)
class HousePartial:
    last_name: str
    first_name: str
    district: int
    hometown: str
    party: str
    voice: str
    room: str
    url: str
    # Additional Fields (not displayed on webpage)
    # leadership_position: str # LeadershipPositionCurrent # EX: "Assistant Majority Floor Leader"
    # year_elected: str # YearEnter # datetime YYYY
    # floor: str # Floor # int 1,2,3,4
    # gender: str # Gender # str M,F


def extract_csv(response):
    """aka ASP.net hoops"""
    # This is effectively submitting a form to extract the CSV file we're after.
    # The cost is making 2 requests instead of 1. The benefit is a CSV file with additional fields.
    # The same could be done (albeit much more verbosely) by using a spatula.URL POST.
    # We would need to scrape the `value` attr for each #id=["__VIEWSTATE", "__EVENTVALIDATION", "btnCSV"]
    # anyway, so making 2 requests is unavoidable, assuming VIEWSTATE and EVENTVALIDATION are dynamic
    # ("btnCSV" should always = "CSV")
    #
    # Note: This process _should_ also work for house committees with some tweaking

    doc = lxml.html.fromstring(response.text, response.url)
    doc = lxml.html.make_links_absolute(doc)
    # there is only one form on the page
    form_response = lxml.html.submit_form(doc.forms[0], extra_values={"btnCSV": "CSV"})
    csv_doc = lxml.html.parse(form_response).getroot()
    return csv_doc


class HouseList(CsvListPage):
    # note: there is a CSV, that requires a form submission to obtain
    source = URL("https://house.mo.gov/MemberGridCluster.aspx?year=2021&code=R+&filter=clear")
    _member_base_url = "https://house.mo.gov/MemberDetails.aspx?year=2021&code=R&district={}"

    def postprocess_response(self):
        csv_doc = extract_csv(self.response)
        self.reader = csv.DictReader(io.StringIO(csv_doc.text_content()))

    def process_item(self, row):
        if not row:
            self.skip()
        if row["LastName"] == "Vacant":
            self.skip()

        return HouseDetail(
            HousePartial(
                last_name=row["LastName"],
                first_name=row["FirstName"],
                district=int(row["District"]),
                party=row["Party"],
                hometown=row["HomeTown"].strip(),
                voice=row["Phone"],
                room=row["Room"],
                url=self._member_base_url.format(row["District"]),
            )
        )


class HouseDetail(HtmlPage):
    input_type = HousePartial

    def process_page(self):
        party = {"Democrat": "Democratic", "Republican": "Republican"}[self.input.party]

        photo = CSS("img#ContentPlaceHolder1_imgPhoto1").match_one(self.root).get("src")
        email = CSS('a[href^="mailto:"]').match_one(self.root).get("href").replace("mailto:", "")

        p = Person(
            state="mo",
            party=party,
            image=photo,
            chamber="lower",
            district=self.input.district,
            name=f"{self.input.first_name} {self.input.last_name}",
            given_name=self.input.first_name,
            family_name=self.input.last_name,
            email=email,
        )
        # TODO
        # p.extras["hometown"] = self.input.hometown
        p.capitol_office.voice = self.input.voice
        p.capitol_office.address = (
            "MO House of Representatives; 201 West Capitol Avenue; "
            f"Room {self.input.room}; Jefferson City MO 65101 "
        )
        p.add_link(self.input.url)
        p.add_source(self.input.url)
        return p


house_members = PeopleWorkflow(HouseList)
