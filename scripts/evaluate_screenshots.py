"""Inspect a local screenshot dataset; optionally score supplied predictions.

Usage: python scripts/evaluate_screenshots.py DATASET_ROOT [--predictions FILE]
The script reads local files only. It neither captures screens nor runs the
application's recognizers, and never generates or rewrites annotations.
"""

import argparse
import json
from pathlib import Path
import sys

# Support running this checkout directly without installing the application.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lootlizard.dataset import (  # noqa: E402
    DatasetError, evaluate_predictions, inventory, load_dataset,
    load_predictions, validate_files,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate manually annotated local PUBG screenshots and report coverage")
    parser.add_argument("dataset_root", type=Path)
    parser.add_argument("--manifest", default="manifest.json", help="Manifest path relative to the dataset root")
    parser.add_argument("--predictions", type=Path, help="Optional explicit prediction JSON; no detector runs automatically")
    parser.add_argument("--tolerance-px", type=float, default=8.0)
    parser.add_argument("--skip-hashes", action="store_true", help="Skip content hashes while still checking images and coordinates")
    parser.add_argument("--output", type=Path, help="Write the JSON report to this file; otherwise print it")
    args = parser.parse_args(argv)
    try:
        dataset = load_dataset(args.dataset_root, args.manifest)
        issues = validate_files(dataset, verify_hashes=not args.skip_hashes)
        report = {"schema_version": 1, "inventory": inventory(dataset),
                  "validation": {"hashes_checked": not args.skip_hashes, "issues": issues},
                  "evaluation": None,
                  "evaluation_status": "No prediction input; accuracy has not been evaluated"}
        if args.predictions:
            if issues:
                report["evaluation_status"] = "Dataset file validation failed; accuracy has not been evaluated"
            else:
                report["evaluation"] = evaluate_predictions(
                    dataset, load_predictions(args.predictions), tolerance_px=args.tolerance_px)
                report["evaluation_status"] = "Scored only explicitly known manual annotations; see coverage and unknown counts"
        text = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
        else:
            print(text, end="")
        return 1 if issues else 0
    except (DatasetError, OSError, ValueError) as error:
        parser.exit(2, f"Dataset error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
