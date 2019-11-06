import sys
import glob
from utils import load_yaml, dump_obj

for f in glob.glob(sys.argv[1] + "/*.yml"):
    obj = load_yaml(open(f))
    for source in obj["sources"]:
        for k in set(source.keys()) - {"url", "note"}:
            source.pop(k)
    dump_obj(obj, output_dir=sys.argv[1])
