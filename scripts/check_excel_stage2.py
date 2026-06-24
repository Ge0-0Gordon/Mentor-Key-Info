"""Print a non-sensitive Stage 2 Excel parsing summary."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mentor_agent.excel_io import load_mentor_inputs_with_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate a mentor Excel file without calling a model or writing outputs."
    )
    parser.add_argument("excel_path", type=Path)
    args = parser.parse_args()

    report = load_mentor_inputs_with_report(args.excel_path)
    print(json.dumps(report.summary.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
