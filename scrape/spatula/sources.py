class Source:
    pass


class URL(Source):
    def __init__(self, url, method="GET", data=None, headers=None):
        self.url = url
        self.method = method
        self.data = data
        self.headers = headers

    def get_data(self, scraper):
        return scraper.request(
            method=self.method, url=self.url, data=self.data, headers=self.headers
        ).content

    def __str__(self):
        return self.url


class NullSource(Source):
    def get_data(self, scraper):
        return None

    def __str__(self):
        return self.__class__.__name__
