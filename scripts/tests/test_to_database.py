import pytest
import yaml
from opencivicdata.core.models import Person, Organization, Jurisdiction, Division
from to_database import load_person


@pytest.mark.django_db
def test_basic_creation():
    data = yaml.load("""
    id: abcdefab-0000-1111-2222-1234567890ab
    name: Jane Smith
    image: https://example.com/image
    extras:
        something: special
    """)

    created, updated = load_person(data)

    assert created is True
    p = Person.objects.get(pk='abcdefab-0000-1111-2222-1234567890ab')
    assert p.name == 'Jane Smith'
    assert p.image == 'https://example.com/image'
    assert p.extras['something'] == 'special'


@pytest.mark.django_db
def test_basic_updates():
    yaml_text = """
    id: abcdefab-0000-1111-2222-1234567890ab
    name: Jane Smith
    image: https://example.com/image
    extras:
        something: special
    """
    data = yaml.load(yaml_text)

    created, updated = load_person(data)
    p = Person.objects.get(pk='abcdefab-0000-1111-2222-1234567890ab')
    created_at, updated_at = p.created_at, p.updated_at

    # ensure no change means no change
    created, updated = load_person(data)
    assert created is False
    assert updated is False
    p = Person.objects.get(pk='abcdefab-0000-1111-2222-1234567890ab')
    assert p.created_at == created_at
    assert p.updated_at == updated_at

    # ensure extra changes got captured
    data['extras']['something'] = 'changed'
    created, updated = load_person(data)
    assert created is False
    assert updated is True
    p = Person.objects.get(pk='abcdefab-0000-1111-2222-1234567890ab')
    assert p.updated_at > updated_at
    assert p.extras['something'] == 'changed'


@pytest.mark.django_db
def test_basic_subobjects():
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
    p = Person.objects.get(pk='abcdefab-0000-1111-2222-1234567890ab')

    assert p.links.count() == 2
    assert p.links.filter(note='some additional data').count() == 1
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
    p = Person.objects.get(pk='abcdefab-0000-1111-2222-1234567890ab')
    created_at, updated_at = p.created_at, p.updated_at

    # ensure no change means no change
    created, updated = load_person(data)
    assert created is False
    assert updated is False
    p = Person.objects.get(pk='abcdefab-0000-1111-2222-1234567890ab')
    assert p.created_at == created_at
    assert p.updated_at == updated_at

    # change one field
    data['links'][0]['url'] = 'https://example.com/jane-smith'
    created, updated = load_person(data)

    assert created is False
    assert updated is True
    p = Person.objects.get(pk='abcdefab-0000-1111-2222-1234567890ab')
    assert p.links.count() == 2
    assert p.links.filter(url='https://example.com/jane-smith').count() == 1
    assert p.updated_at > updated_at

    # delete a field
    data['links'].pop()
    created, updated = load_person(data)
    assert created is False
    assert updated is True
    p = Person.objects.get(pk='abcdefab-0000-1111-2222-1234567890ab')
    assert p.links.count() == 1
    assert p.updated_at > updated_at


@pytest.mark.django_db
def test_identifiers():
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
    p = Person.objects.get(pk='abcdefab-0000-1111-2222-1234567890ab')

    assert p.identifiers.count() == 4
    assert p.identifiers.filter(scheme='old_openstates').count() == 2
    assert p.identifiers.filter(scheme='twitter')[0].identifier == 'fakeaccount'


@pytest.mark.django_db
def test_contact_details():
    yaml_text = """
    id: abcdefab-0000-1111-2222-1234567890ab
    name: Jane Smith
    contact_details:
        - note: district office
          fax: 111-222-3333
          voice: 555-555-5555
          email: fake@example.com
          address: 123 Main St; Washington DC; 20001
        - note: home
          voice: 333-333-3333
    """
    data = yaml.load(yaml_text)

    created, updated = load_person(data)
    p = Person.objects.get(pk='abcdefab-0000-1111-2222-1234567890ab')

    assert p.contact_details.count() == 5
    assert p.contact_details.filter(note='home').count() == 1


@pytest.mark.django_db
def test_party():
    yaml_text = """
    id: abcdefab-0000-1111-2222-1234567890ab
    name: Jane Smith
    party:
        - name: Democratic
    """
    data = yaml.load(yaml_text)
    Organization.objects.create(name='Democratic', classification='party')
    Organization.objects.create(name='Republican', classification='party')

    created, updated = load_person(data)
    p = Person.objects.get(pk='abcdefab-0000-1111-2222-1234567890ab')

    assert p.memberships.count() == 1
    assert p.memberships.get().organization.name == 'Democratic'

    data['party'].append({'name': 'Republican', 'end_date': '2018-10-06'})
    created, updated = load_person(data)
    assert updated is True
    p = Person.objects.get(pk='abcdefab-0000-1111-2222-1234567890ab')
    p.memberships.count() == 2
    p.memberships.exclude(end_date='').count() == 1


@pytest.mark.django_db
def test_legislative_roles():
    yaml_text = """
    id: abcdefab-0000-1111-2222-1234567890ab
    name: Jane Smith
    roles:
        - type: lower
          district: 3
          jurisdiction: ocd-jurisdiction/country:us/state:nc
    """
    data = yaml.load(yaml_text)
    d = Division.objects.create(id='ocd-division/country:us/state:nc', name='NC')
    j = Jurisdiction.objects.create(id='ocd-jurisdiction/country:us/state:nc', name='NC',
                                    division=d)
    o = Organization.objects.create(name='House', classification='lower', jurisdiction=j)
    o.posts.create(label='3')

    created, updated = load_person(data)
    p = Person.objects.get(pk='abcdefab-0000-1111-2222-1234567890ab')

    assert p.memberships.count() == 1
    assert p.memberships.get().organization.name == 'House'
    assert p.memberships.get().post.label == '3'

# TODO: committees & executives
