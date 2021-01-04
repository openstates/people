import re


def elem_to_str(item, inside=False):
    attribs = "  ".join(f"{k}='{v}'" for k, v in item.attrib.items())
    return f"<{item.tag} {attribs}> @ line {item.sourceline}"


class SelectorError(ValueError):
    pass


class Selector:
    def __init__(self, *, min_items=1, max_items=None, num_items=None):
        self.min_items = min_items
        self.max_items = max_items
        self.num_items = num_items

    def match(self, element, *, min_items=None, max_items=None, num_items=None):
        items = list(self.get_items(element))
        num_items = self.num_items if num_items is None else num_items
        max_items = self.max_items if max_items is None else max_items
        min_items = self.min_items if min_items is None else min_items

        if num_items is not None and len(items) != num_items:
            raise SelectorError(
                f"{self.get_display()} on {elem_to_str(element)} got {len(items)}, "
                f"expected {num_items}"
            )
        if min_items is not None and len(items) < min_items:
            raise SelectorError(
                f"{self.get_display()} on {elem_to_str(element)} got {len(items)}, "
                f"expected at least {min_items}"
            )
        if max_items is not None and len(items) > max_items:
            raise SelectorError(
                f"{self.get_display()} on {elem_to_str(element)} got {len(items)}, "
                f"expected at most {max_items}"
            )

        return items

    def match_one(self, element):
        return self.match(element, num_items=1)[0]


class XPath(Selector):
    def __init__(self, xpath, *, min_items=1, max_items=None, num_items=None):
        super().__init__(min_items=min_items, max_items=max_items, num_items=num_items)
        self.xpath = xpath

    def get_items(self, element):
        yield from element.xpath(self.xpath)

    def get_display(self):
        return f"XPath({self.xpath})"


class SimilarLink(Selector):
    def __init__(self, pattern, *, min_items=1, max_items=None, num_items=None):
        super().__init__(min_items=min_items, max_items=max_items, num_items=num_items)
        self.pattern = re.compile(pattern)

    def get_items(self, element):
        seen = set()
        for element in element.xpath("//a"):
            href = element.get("href")
            if href and href not in seen and self.pattern.match(element.get("href", "")):
                yield element
                seen.add(href)

    def get_display(self):
        return f"SimilarLink({self.pattern})"


class CSS(Selector):
    def __init__(self, css_selector, *, min_items=1, max_items=None, num_items=None):
        super().__init__(min_items=min_items, max_items=max_items, num_items=num_items)
        self.css_selector = css_selector

    def get_items(self, element):
        yield from element.cssselect(self.css_selector)

    def get_display(self):
        return f"CSS({self.css_selector})"
