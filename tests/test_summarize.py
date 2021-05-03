from ospeople.cli.summarize import Summarizer


def test_person_summary():
    s = Summarizer()

    people = [
        {
            "gender": "F",
            "image": "https://example.com/image1",
            "party": [{"name": "Democratic"}, {"name": "Democratic", "end_date": "1990"}],
        },
        {
            "gender": "F",
            "image": "https://example.com/image2",
            "party": [{"name": "Democratic"}, {"name": "Working Families"}],
            "extras": {"religion": "Zoroastrian"},
            "contact_details": [{"fax": "123-456-7890", "note": "Capitol Office"}],
            "other_identifiers": [{"scheme": "fake", "identifier": "abc"}],
            "ids": {"twitter": "fake"},
        },
        {
            "gender": "M",
            "image": "https://example.com/image3",
            "party": [{"name": "Republican"}],
            "contact_details": [{"phone": "123-456-7890", "note": "Capitol Office"}],
            "other_identifiers": [{"scheme": "fake", "identifier": "123"}],
        },
    ]

    for p in people:
        s.summarize(p)

    assert s.parties == {"Republican": 1, "Democratic": 2, "Working Families": 1}
    assert s.contact_counts == {"Capitol Office phone": 1, "Capitol Office fax": 1}
    assert s.id_counts == {"fake": 2, "twitter": 1}
    assert s.optional_fields == {"gender": 3, "image": 3}
    assert s.extra_counts == {"religion": 1}
