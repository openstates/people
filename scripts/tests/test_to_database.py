import pytest
import yaml
from opencivicdata.core.models import Person, Organization, Jurisdiction, Division, Post
from to_database import load_person, load_org, create_juris_orgs_posts


def setup():
    d = Division.objects.create(id="ocd-division/country:us/state:nc", name="NC")
    j = Jurisdiction.objects.create(
        id="ocd-jurisdiction/country:us/state:nc", name="NC", division=d
    )
    o = Organization.objects.create(name="House", classification="lower", jurisdiction=j)
    o.posts.create(label="1")
    o.posts.create(label="2")
    o.posts.create(label="3")
    Organization.objects.create(name="Democratic", classification="party")
    Organization.objects.create(name="Republican", classification="party")


@pytest.mark.django_db
def test_basic_person_creation():
    data = yaml.load(
        """
    id: abcdefab-0000-1111-2222-1234567890ab
    name: Jane Smith
    image: https://example.com/image
    extras:
        something: special
    """
    )

    created, updated = load_person(data)

    assert created is True
    p = Person.objects.get(pk="abcdefab-0000-1111-2222-1234567890ab")
    assert p.name == "Jane Smith"
    assert p.image == "https://example.com/image"
    assert p.extras["something"] == "special"


@pytest.mark.django_db
def test_basic_person_updates():
    yaml_text = """
    id: abcdefab-0000-1111-2222-1234567890ab
    name: Jane Smith
    image: https://example.com/image
    extras:
        something: special
    """
    data = yaml.load(yaml_text)

    created, updated = load_person(data)
    p = Person.objects.get(pk="abcdefab-0000-1111-2222-1234567890ab")
    created_at, updated_at = p.created_at, p.updated_at

    # ensure no change means no change
    created, updated = load_person(data)
    assert created is False
    assert updated is False
    p = Person.objects.get(pk="abcdefab-0000-1111-2222-1234567890ab")
    assert p.created_at == created_at
    assert p.updated_at == updated_at

    # ensure extra changes got captured
    data["extras"]["something"] = "changed"
    created, updated = load_person(data)
    assert created is False
    assert updated is True
    p = Person.objects.get(pk="abcdefab-0000-1111-2222-1234567890ab")
    assert p.updated_at > updated_at
    assert p.extras["something"] == "changed"


@pytest.mark.django_db
def test_basic_person_subobjects():
    yaml_text = """
    id: abcdefab-0000-1111-2222-1234567890ab
    name: Jane Smith
    links:
        - url: https://example.com/jane
        - url: https://example.com/extra
          note: some additional data
    sources:
        - url: https://example.com/jane
    other_names:
        - name: J. Smith
    """
    data = yaml.load(yaml_text)

    created, updated = load_person(data)
    p = Person.objects.get(pk="abcdefab-0000-1111-2222-1234567890ab")

    assert p.links.count() == 2
    assert p.links.filter(note="some additional data").count() == 1
    assert p.sources.count() == 1
    assert p.other_names.count() == 1


@pytest.mark.django_db
def test_subobject_update():
    yaml_text = """
    id: abcdefab-0000-1111-2222-1234567890ab
    name: Jane Smith
    links:
        - url: https://example.com/jane
        - url: https://example.com/extra
          note: some additional data
    """
    data = yaml.load(yaml_text)

    created, updated = load_person(data)
    p = Person.objects.get(pk="abcdefab-0000-1111-2222-1234567890ab")
    created_at, updated_at = p.created_at, p.updated_at

    # ensure no change means no change
    created, updated = load_person(data)
    assert created is False
    assert updated is False
    p = Person.objects.get(pk="abcdefab-0000-1111-2222-1234567890ab")
    assert p.created_at == created_at
    assert p.updated_at == updated_at

    # change one field
    data["links"][0]["url"] = "https://example.com/jane-smith"
    created, updated = load_person(data)

    assert created is False
    assert updated is True
    p = Person.objects.get(pk="abcdefab-0000-1111-2222-1234567890ab")
    assert p.links.count() == 2
    assert p.links.filter(url="https://example.com/jane-smith").count() == 1
    assert p.updated_at > updated_at

    # delete a field
    data["links"].pop()
    created, updated = load_person(data)
    assert created is False
    assert updated is True
    p = Person.objects.get(pk="abcdefab-0000-1111-2222-1234567890ab")
    assert p.links.count() == 1
    assert p.updated_at > updated_at


@pytest.mark.django_db
def test_subobject_duplicate():
    # this shouldn't actually be allowed most places (lint should catch)
    # but it was breaking committee imports when two members had the same name
    yaml_text = """
    id: abcdefab-0000-1111-2222-1234567890ab
    name: Jane Smith
    links:
        - url: https://example.com/jane
        - url: https://example.com/jane
    """
    data = yaml.load(yaml_text)

    # load twice, but second time no update should occur
    created, updated = load_person(data)
    created, updated = load_person(data)
    assert created is False
    assert updated is False


@pytest.mark.django_db
def test_person_identifiers():
    yaml_text = """
    id: abcdefab-0000-1111-2222-1234567890ab
    name: Jane Smith
    ids:
        twitter: fakeaccount
        youtube: fakeYT
    other_identifiers:
        - scheme: old_openstates
          identifier: AR000001
        - scheme: old_openstates
          identifier: AR000002
    """
    data = yaml.load(yaml_text)

    created, updated = load_person(data)
    p = Person.objects.get(pk="abcdefab-0000-1111-2222-1234567890ab")

    assert p.identifiers.count() == 4
    assert p.identifiers.filter(scheme="old_openstates").count() == 2
    assert p.identifiers.filter(scheme="twitter")[0].identifier == "fakeaccount"


@pytest.mark.django_db
def test_person_contact_details():
    yaml_text = """
    id: abcdefab-0000-1111-2222-1234567890ab
    name: Jane Smith
    contact_details:
        - note: Capitol Office office
          fax: 111-222-3333
          voice: 555-555-5555
          email: fake@example.com
          address: 123 Main St; Washington DC; 20001
        - note: home
          voice: 333-333-3333
    """
    data = yaml.load(yaml_text)

    created, updated = load_person(data)
    p = Person.objects.get(pk="abcdefab-0000-1111-2222-1234567890ab")

    assert p.contact_details.count() == 5
    assert p.contact_details.filter(note="home").count() == 1


@pytest.mark.django_db
def test_person_party():
    yaml_text = """
    id: abcdefab-0000-1111-2222-1234567890ab
    name: Jane Smith
    party:
        - name: Democratic
    """
    data = yaml.load(yaml_text)

    created, updated = load_person(data)
    p = Person.objects.get(pk="abcdefab-0000-1111-2222-1234567890ab")

    assert p.memberships.count() == 1
    assert p.memberships.get().organization.name == "Democratic"

    data["party"].append({"name": "Republican", "end_date": "2018-10-06"})
    created, updated = load_person(data)
    assert updated is True
    p = Person.objects.get(pk="abcdefab-0000-1111-2222-1234567890ab")
    p.memberships.count() == 2
    p.memberships.exclude(end_date="").count() == 1


@pytest.mark.django_db
def test_person_legislative_roles():
    yaml_text = """
    id: abcdefab-0000-1111-2222-1234567890ab
    name: Jane Smith
    roles:
        - type: lower
          district: 3
          jurisdiction: ocd-jurisdiction/country:us/state:nc
    """
    data = yaml.load(yaml_text)
    created, updated = load_person(data)
    p = Person.objects.get(pk="abcdefab-0000-1111-2222-1234567890ab")

    assert p.memberships.count() == 1
    assert p.memberships.get().organization.name == "House"
    assert p.memberships.get().post.label == "3"


EXAMPLE_ORG_ID = "ocd-organization/00000000-1111-2222-3333-444455556666"


@pytest.mark.django_db
def test_basic_organization():
    data = yaml.load(
        """
    id: ocd-organization/00000000-1111-2222-3333-444455556666
    name: Finance
    parent: lower
    jurisdiction: ocd-jurisdiction/country:us/state:nc
    classification: committee
    founding_date: '2007-01-01'
    """
    )
    created, updated = load_org(data)

    assert created is True
    o = Organization.objects.get(pk=EXAMPLE_ORG_ID)
    assert o.name == "Finance"
    assert o.jurisdiction.name == "NC"
    assert o.parent.name == "House"


@pytest.mark.django_db
def test_basic_organization_updates():
    data = yaml.load(
        """
    id: ocd-organization/00000000-1111-2222-3333-444455556666
    name: Finance
    parent: lower
    jurisdiction: ocd-jurisdiction/country:us/state:nc
    classification: committee
    founding_date: '2007-01-01'
    """
    )
    created, updated = load_org(data)
    o = Organization.objects.get(pk=EXAMPLE_ORG_ID)
    created_at, updated_at = o.created_at, o.updated_at

    # ensure no change means no change
    created, updated = load_org(data)
    assert created is False
    assert updated is False
    o = Organization.objects.get(pk=EXAMPLE_ORG_ID)
    assert o.created_at == created_at
    assert o.updated_at == updated_at

    # ensure extra changes got captured
    data["founding_date"] = "2008-01-01"
    created, updated = load_org(data)
    assert created is False
    assert updated is True
    o = Organization.objects.get(pk=EXAMPLE_ORG_ID)
    assert o.updated_at > updated_at
    assert o.founding_date == "2008-01-01"


@pytest.mark.django_db
def test_organization_memberships():
    data = yaml.load(
        """
    id: ocd-organization/00000000-1111-2222-3333-444455556666
    name: Finance
    parent: lower
    jurisdiction: ocd-jurisdiction/country:us/state:nc
    classification: committee
    founding_date: '2007-01-01'
    memberships:
        - id: 123
          name: Jane Smith
        - name: Noah Idy
    """
    )
    Person.objects.create(id="123", name="Jane Smith")
    created, updated = load_org(data)
    o = Organization.objects.get(pk=EXAMPLE_ORG_ID)
    assert o.memberships.count() == 2

    data["memberships"].append({"name": "Another One", "role": "Chairman"})
    created, updated = load_org(data)
    assert created is False
    assert updated is True
    assert o.memberships.count() == 3
    assert o.memberships.filter(role="Chairman")[0].person_name == "Another One"

    data["memberships"] = []
    created, updated = load_org(data)
    assert created is False
    assert updated is True
    assert o.memberships.count() == 0


@pytest.mark.django_db
def test_org_person_membership_interaction():
    # this test ensure that committee memberships don't mess up person loading
    person_data = {"id": "123", "name": "Jane Smith"}
    com_data = yaml.load(
        """
    id: ocd-organization/00000000-1111-2222-3333-444455556666
    name: Finance
    parent: lower
    jurisdiction: ocd-jurisdiction/country:us/state:nc
    classification: committee
    founding_date: '2007-01-01'
    memberships:
        - id: 123
          name: Jane Smith
    """
    )
    load_person(person_data)
    load_org(com_data)
    o = Organization.objects.get(pk=EXAMPLE_ORG_ID)
    assert o.memberships.count() == 1

    # re-import person, make sure it doesn't count as an update and that the membership persists
    #  (this corresponds to the use of read_manager in update_subobjects)
    created, updated = load_person(person_data)
    assert created is False
    assert updated is False
    assert o.memberships.count() == 1


@pytest.mark.django_db
def test_create_juris_orgs_posts_simple():
    d = Division.objects.create(id="ocd-division/country:us/state:al", name="Alabama")
    j = Jurisdiction.objects.create(
        id="ocd-jurisdiction/country:us/state:al/government", name="Alabama", division=d
    )
    Organization.objects.create(jurisdiction=j, name="House", classification="lower")
    Organization.objects.create(jurisdiction=j, name="Senate", classification="upper")
    # divisions would already exist
    for n in range(1, 35 + 1):
        Division.objects.create(id=f"ocd-division/country:us/state:al/sldu:{n}", name=str(n))
    for n in range(1, 105 + 1):
        Division.objects.create(id=f"ocd-division/country:us/state:al/sldl:{n}", name=str(n))

    create_juris_orgs_posts(j.id)

    assert Post.objects.filter(role="Senator").count() == 35
    assert Post.objects.filter(role="Representative").count() == 105


@pytest.mark.django_db
def test_create_top_level_unicameral():
    d = Division.objects.create(id="ocd-division/country:us/district:dc", name="DC")
    j = Jurisdiction.objects.create(
        id="ocd-jurisdiction/country:us/district:dc/government", name="DC", division=d
    )
    org = Organization.objects.create(jurisdiction=j, name="Council", classification="legislature")
    for n in range(1, 9):
        Division.objects.create(
            id=f"ocd-division/country:us/district:dc/ward:{n}", name=f"Ward {n}"
        )

    create_juris_orgs_posts(j.id)
    assert org.posts.all().count() == 10
    assert Post.objects.filter(division_id="ocd-division/country:us/district:dc").count() == 2
