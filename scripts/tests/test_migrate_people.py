from migrate_people import terms_to_roles

nc_terms = [
    {"end_year": 2010, "start_year": 2009, "name": "2009-2010", "sessions": ["2009"]},
    {"end_year": 2012, "start_year": 2011, "name": "2011-2012", "sessions": ["2011"]},
    {"end_year": 2014, "start_year": 2013, "name": "2013-2014", "sessions": ["2013"]},
    {
        "end_year": 2016,
        "start_year": 2015,
        "name": "2015-2016",
        "sessions": ["2015", "2015E1", "2015E2", "2015E3", "2015E4", "2015E5"],
    },
    {
        "end_year": 2018,
        "start_year": 2017,
        "name": "2017-2018",
        "sessions": ["2017", "2017E1", "2017E2", "2017E3"],
    },
]


def test_terms_to_roles_simple():
    leg_terms = [
        {"term": "2009-2010", "chamber": "upper", "district": "1"},
        {"term": "2011-2012", "chamber": "upper", "district": "1"},
        # redistricting
        {"term": "2013-2014", "chamber": "upper", "district": "2"},
        # lost election, then came back
        {"term": "2017-2018", "chamber": "upper", "district": "2"},
    ]
    result = terms_to_roles(leg_terms, nc_terms)
    assert result == [
        ("upper", "1", 2009, 2012),
        ("upper", "2", 2013, 2014),
        ("upper", "2", 2017, 2018),
    ]
