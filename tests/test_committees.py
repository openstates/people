import pytest
from pathlib import Path
from pydantic import ValidationError
from ospeople.cli.committees import CommitteeDir
from ospeople.models.committees import Committee, Link, ScrapeCommittee, Membership


def test_load_data():
    comdir = CommitteeDir(abbr="wa", directory=Path("tests/testdata/committees"))

    assert len(comdir.coms_by_chamber_and_name["lower"]) == 2
    assert len(comdir.coms_by_chamber_and_name["upper"]) == 1
    assert comdir.errors == []


def test_load_data_with_errors():
    comdir = CommitteeDir(
        abbr="wa", directory=Path("tests/testdata/broken-committees"), raise_errors=False
    )

    assert len(comdir.coms_by_chamber_and_name["lower"]) == 0
    assert len(comdir.coms_by_chamber_and_name["upper"]) == 0
    assert len(comdir.errors) == 2
    path0, msg0 = comdir.errors[0]
    assert "8 validation errors" in str(msg0)
    assert "members -> 3 -> who" in str(msg0)
    assert "members -> 3 -> name" in str(msg0)
    path1, msg1 = comdir.errors[1]
    assert "2 validation errors" in str(msg1)
    assert "value is not a valid enumeration member" in str(msg1)
    assert "extra fields not permitted" in str(msg1)


def test_load_data_with_errors_raised():
    # default is to raise error right away, test_load_data_with_errors catches errors for linter
    with pytest.raises(ValidationError):
        CommitteeDir(
            abbr="wa",
            directory=Path("tests/testdata/broken-committees"),
        )


def test_get_new_filename():
    comdir = CommitteeDir(
        abbr="wa",
        directory=Path("tests/testdata/committees"),
    )
    simple = Committee(
        id="ocd-organization/00001111-2222-3333-4444-555566667777",
        name="Simple",
        parent="lower",
    )
    longer = Committee(
        id="ocd-organization/00001111-2222-3333-4444-999999999999",
        name="Ways, Means & Taxes",
        parent="upper",
    )
    assert (
        comdir.get_new_filename(simple) == "lower-Simple-00001111-2222-3333-4444-555566667777.yml"
    )
    assert (
        comdir.get_new_filename(longer)
        == "upper-Ways-Means--Taxes-00001111-2222-3333-4444-999999999999.yml"
    )


def test_get_filename_by_id():
    comdir = CommitteeDir(
        abbr="wa",
        directory=Path("tests/testdata/committees"),
    )
    assert (
        str(comdir.get_filename_by_id("ocd-organization/11111111-2222-3333-4444-111111111111"))
        == "tests/testdata/committees/lower-Agriculture-11111111-2222-3333-4444-111111111111.yml"
    )

    with pytest.raises(FileNotFoundError):
        comdir.get_filename_by_id("ocd-organization/99999999-9999-9999-9999-999999999999")


def test_get_filename_by_name():
    comdir = CommitteeDir(
        abbr="wa",
        directory=Path("tests/testdata/committees"),
    )
    assert (
        str(comdir.get_filename_by_name("lower", "Agriculture"))
        == "tests/testdata/committees/lower-Agriculture-11111111-2222-3333-4444-111111111111.yml"
    )

    with pytest.raises(FileNotFoundError):
        comdir.get_filename_by_name("lower", "Weird")


# TODO: test_save_committee, test_add_committee


def test_ingest_scraped_json():
    comdir = CommitteeDir(
        abbr="wa",
        directory=Path("tests/testdata/committees"),
    )
    committees = comdir.ingest_scraped_json("tests/testdata/scraped-committees")
    assert len(committees) == 2
    assert committees[0].name == "Judiciary 2"
    assert committees[1].name == "Judiciary 4"


def test_get_merge_plan_by_chamber():
    comdir = CommitteeDir(
        abbr="wa",
        directory=Path("tests/testdata/committees"),
    )

    newdata = [
        ScrapeCommittee(
            name="Education",
            parent="lower",
            sources=[Link(url="https://example.com/committee")],
            members=[
                Membership(name="Jones", role="chair"),
                Membership(name="Nguyen", role="co-chair"),
                Membership(name="Green", role="member"),
                Membership(name="Cristobal", role="member"),
            ],
        ),
        ScrapeCommittee(
            name="Science",
            parent="lower",
            sources=[Link(url="https://example.com/committee")],
            members=[
                Membership(name="Jones", role="chair"),
                Membership(name="Nguyen", role="co-chair"),
            ],
        ),
    ]

    plan = comdir.get_merge_plan_by_chamber("lower", newdata)
    assert plan.names_to_add == {"Science"}
    assert plan.names_to_remove == {"Agriculture"}
    assert plan.to_merge == []  # TODO: add one to merge
    assert plan.same == 1
