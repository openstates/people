from utils import get_filename


class ListDifference:
    def __init__(self, key_name, list_item, which_list):
        self.key_name = key_name
        self.list_item = list_item
        self.which_list = which_list

    def __eq__(self, other):
        return (self.key_name == other.key_name and
                self.list_item == other.list_item and
                self.which_list == other.which_list)


class ItemDifference:
    def __init__(self, key_name, value_one, value_two):
        self.key_name = key_name
        self.value_one = value_one
        self.value_two = value_two

    def __eq__(self, other):
        return (self.key_name == other.key_name and
                self.value_one == other.value_one and
                self.value_two == other.value_two)


def compare_objects(obj1, obj2, prefix=''):
    combined_keys = set(obj1) | set(obj2)
    differences = []
    for key in combined_keys:
        key_name = '.'.join((prefix, key)) if prefix else key
        val1 = obj1.get(key)
        val2 = obj2.get(key)
        if isinstance(val1, list) or isinstance(val2, list):
            # we can compare this way since order doesn't matter
            for item in val1:
                if item not in val2:
                    differences.append(ListDifference(key_name, item, 'first'))
            for item in val2:
                if item not in val1:
                    differences.append(ListDifference(key_name, item, 'second'))
        elif isinstance(val1, dict) or isinstance(val2, dict):
            differences.extend(compare_objects(val1 or {}, val2 or {}, prefix=key_name))
        elif val1 != val2:
            differences.append(ItemDifference(key_name, val1, val2))
    return differences


def calculate_similarity(existing, new):
    differences = compare_objects(existing, new)

    # if nothing differs or only id differs
    if len(differences) == 0 or (len(differences) == 1 and differences[0].key_name == 'id'):
        return 1

    if len(differences) < 2:
        return 0.9

    return 0


def directory_merge(existing_people, new_people, threshold=90):
    perfect_matches = []
    unmatched = set()
    matched = set()

    for new in new_people:
        unmatched.add(new['id'])
        for existing in existing_people:
            similarity = calculate_similarity(existing, new)
            if similarity == 100:
                perfect_matches.append(similarity)
            elif similarity > threshold:
                print('likely match: {} with new {}'.format(
                    get_filename(existing), get_filename(new)
                ))
                matched.add(new['id'])

    unmatched -= matched
