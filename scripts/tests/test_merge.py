import pytest
from merge import (compare_objects, ItemDifference, ListDifference, calculate_similarity,
                   merge_people, MergeConflict)


@pytest.mark.parametrize("a, b, output", [
    # no errors
    ({'a': 'one', 'b': 'two'}, {'a': 'one', 'b': 'two'}, []),
    # simple error
    ({'a': 'one', 'b': 'two'}, {'a': 'bad', 'b': 'two'}, [ItemDifference('a', 'one', 'bad')]),
    # missing key from first
    ({'a': 'one'}, {'a': 'one', 'b': 'two'}, [ItemDifference('b', None, 'two')]),
    # missing key from second
    ({'a': 'one', 'b': 'two'}, {'a': 'one'}, [ItemDifference('b', 'two', None)]),
])
def test_compare_objects_simple(a, b, output):
    assert compare_objects(a, b) == output


@pytest.mark.parametrize("a, b, output", [
    # no errors
    ({'a': {'b': 'c'}}, {'a': {'b': 'c'}}, []),
    # no errors
    ({'a': {'b': 'c'}}, {'a': {}}, [ItemDifference('a.b', 'c', None)]),
])
def test_compare_objects_nested(a, b, output):
    assert compare_objects(a, b) == output


@pytest.mark.parametrize("a, b, output", [
    # no errors
    ({'a': [{'b': 1}, {'c': 2}]}, {'a': [{'b': 1}, {'c': 2}]}, []),
    # no errors - just different order
    ({'a': [{'b': 1}, {'c': 2}]}, {'a': [{'c': 2}, {'b': 1}]}, []),
    # extra item left
    ({'a': [{'b': 1}, {'c': 2}, {'d': 3}]}, {'a': [{'b': 1}, {'c': 2}]},
     [ListDifference('a', {'d': 3},  'first')]),
    # extra item right
    ({'a': [{'b': 1}, {'c': 2}]}, {'a': [{'b': 1}, {'c': 2}, {'d': 3}]},
     [ListDifference('a', {'d': 3},  'second')]),
])
def test_compare_objects_list(a, b, output):
    assert compare_objects(a, b) == output


def test_calculate_similarity():
    base_person = {'id': '123', 'name': 'A. Person',
                   'birth_date': '1980-01-01',
                   'party': [{'name': 'Democratic'}]}

    new_id_person = base_person.copy()
    new_id_person['id'] = '456'
    assert calculate_similarity(base_person, new_id_person) == pytest.approx(1)

    new_name_person = base_person.copy()
    new_name_person['name'] = 'Another Person'
    assert calculate_similarity(base_person, new_name_person) == pytest.approx(0.8)

    new_name_person['death_date'] = '2018-01-01'
    assert calculate_similarity(base_person, new_name_person) == pytest.approx(0.7)

    new_name_person['roles'] = [{'type': 'lower', 'district': '3'}]
    assert calculate_similarity(base_person, new_name_person) == pytest.approx(0.6)


@pytest.mark.parametrize("old, new, keep, expected", [
    # no changes
    ({'name': 'Anna'}, {'name': 'Anna'}, 'old',
     {'name': 'Anna'}),
    # field only in old, keep=old
    ({'name': 'Anna', 'birth_date': '1980'}, {'name': 'Anna'}, 'old',
     {'name': 'Anna', 'birth_date': '1980'}),
    # field only in old, keep=new
    ({'name': 'Anna', 'birth_date': '1980'}, {'name': 'Anna'}, 'new',
     {'name': 'Anna', 'birth_date': '1980'}),
    # field only in new, keep=old
    ({'name': 'Anna'}, {'name': 'Anna', 'birth_date': '1980'}, 'old',
     {'name': 'Anna', 'birth_date': '1980'}),
    # field only in new, keep=new
    ({'name': 'Anna'}, {'name': 'Anna', 'birth_date': '1980'}, 'new',
     {'name': 'Anna', 'birth_date': '1980'}),
    # field differs, keep=new
    ({'name': 'Bob'}, {'name': 'Robert'}, 'new', {'name': 'Robert'}),
    # field differs, keep=old
    ({'name': 'Bob'}, {'name': 'Robert'}, 'old', {'name': 'Bob'}),
])
def test_simple_merge(old, new, keep, expected):
    assert merge_people(old, new, keep) == expected


def test_merge_conflict():
    with pytest.raises(MergeConflict):
        merge_people({'name': 'A'}, {'name': 'B'})


@pytest.mark.parametrize("old, new, expected", [
    # more in first list
    ({'other_names': [{'name': 'A'}, {'name': 'B'}]},
     {'other_names': [{'name': 'A'}]},
     {'other_names': [{'name': 'A'}, {'name': 'B'}]}
     ),
    # more in second list
    ({'other_names': [{'name': 'A'}]},
     {'other_names': [{'name': 'A'}, {'name': 'B'}]},
     {'other_names': [{'name': 'A'}, {'name': 'B'}]}
     ),
    # each list is unique
    ({'other_names': [{'name': 'A'}]},
     {'other_names': [{'name': 'B'}]},
     {'other_names': [{'name': 'A'}, {'name': 'B'}]}
     ),
])
def test_list_merge(old, new, expected):
    # note that keep doesn't matter for these
    assert merge_people(old, new, None) == expected


@pytest.mark.parametrize("old, new, expected", [
    # simplest case
    ({'id': 'ocd-person/1'},
     {'id': 'ocd-person/2'},
     {'id': 'ocd-person/1',
      'other_identifiers': [{'scheme': 'openstates', 'identifier': 'ocd-person/2'}]
      }
     ),
    # already has identifiers
    ({'id': 'ocd-person/1',
      'other_identifiers': [{'scheme': 'openstates', 'identifier': 'ocd-person/0'}]
      },
     {'id': 'ocd-person/2'},
     {'id': 'ocd-person/1',
      'other_identifiers': [
          {'scheme': 'openstates', 'identifier': 'ocd-person/0'},
          {'scheme': 'openstates', 'identifier': 'ocd-person/2'},
      ]
      }
     ),
])
def test_keep_both_ids(old, new, expected):
    assert merge_people(old, new, keep_both_ids=True) == expected
