class Source:
    pass


class URL(Source):
    def __init__(self, url, method="GET", data=None):
        self.url = url
        self.method = method
        self.data = data

    def get_data(self, scraper):
        return scraper.request(method=self.method, url=self.url, data=self.data).content

    def __str__(self):
        return self.url
