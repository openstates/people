import lxml.html
import requests
import datetime
import re

data = requests.get("https://en.wikipedia.org/wiki/List_of_United_States_governors").text
doc = lxml.html.fromstring(data)

for tr in doc.xpath("//table[1]//tr"):
    children = tr.getchildren()
    if len(children) == 10:
        state = children[0].text_content().strip()
        name = children[2].text_content().strip()
        party = children[4].text_content().strip()
        birthdate = re.findall(r"\d{4}-\d{2}-\d{2}", children[5].text_content().strip())[0]
        inauguration = children[7].text_content().strip()
        inauguration = datetime.datetime.strptime(inauguration, "%B %d, %Y").strftime("%Y-%m-%d")
        end_date = children[8].text_content().strip().split()[0]
        # best approximation for now
        if state in ("Alaska", "Hawaii", "North Dakota", "New York", "Kentucky"):
            end_date += "-12-31"
        else:
            end_date += "-01-01"
        print(",".join((state, name, party, birthdate, inauguration, end_date)))
