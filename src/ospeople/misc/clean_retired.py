from ..utils import load_yaml, dump_obj
import sys

for fn in sys.argv[1:]:
    data = load_yaml(open(fn))
    data.pop("contact_details")
    dump_obj(data, filename=fn)
