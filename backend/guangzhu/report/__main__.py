"""Generate a report without starting AGH or calling a model."""
import argparse
import json
from . import generate

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("run_dir")
parser.add_argument("--regenerated", action="store_true")
args = parser.parse_args()
state = generate(args.run_dir, regenerated=args.regenerated)
print(json.dumps(state, ensure_ascii=False))
raise SystemExit(1 if state["status"] == "error" else 0)
