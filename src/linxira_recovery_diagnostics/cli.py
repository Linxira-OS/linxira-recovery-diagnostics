from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from .collector import EvidenceCollector
from .plans import PLAN_IDS, make_plan
from .support import create_support_bundle, preview_manifest, save_plan


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Read-only Linxira recovery diagnostics")
    actions = result.add_mutually_exclusive_group()
    actions.add_argument("--report-json", action="store_true", help="print the schema-v1 evidence report")
    actions.add_argument("--plan", choices=PLAN_IDS, help="save and print one fixed repair plan")
    actions.add_argument("--support-bundle", action="store_true", help="create a private, redacted support bundle")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not (args.report_json or args.plan or args.support_bundle):
        from .gui import main as gui_main
        return gui_main([])
    report = EvidenceCollector().collect()
    if args.report_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.plan:
        plan = make_plan(args.plan, report)
        path = save_plan(plan)
        print(json.dumps({"saved": str(path), "plan": plan}, indent=2, sort_keys=True))
    else:
        manifest = preview_manifest(report)
        path, _ = create_support_bundle(report)
        print(json.dumps({"saved": str(path), "manifest": manifest}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
