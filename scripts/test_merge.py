import pytest
from merge import compare_objects, ItemDifference, ListDifference


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
