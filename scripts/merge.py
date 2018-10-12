from utils import get_filename


def compare_unordered_lists(list1, list2):
    differences = []
    for item in list1:
        if item not in list2:
            differences.append(f'{item} only in first list')
    for item in list2:
        if item not in list1:
            differences.append(f'{item} only in second list')
    return differences


def compare_objects(obj1, obj2):
    combined_keys = set(obj1) | set(obj2)
    differences = []
    for key in combined_keys:
        val1 = obj1.get(key)
        val2 = obj2.get(key)
        if isinstance(val1, list) or isinstance(val2, list):
            differences.extend(compare_unordered_lists(val1 or [], val2 or []))
        elif isinstance(val1, dict) or isinstance(val2, dict):
            differences.extend(compare_objects(val1 or {}, val2 or {}))
        elif val1 != val2:
            differences.append((key, f'{val1} != {val2}'))
    return differences


def calculate_similarity(existing, new):
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
