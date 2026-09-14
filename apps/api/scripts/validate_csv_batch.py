#!/usr/bin/env python3
"""校验学校每日 CSV 批次，不写入正式数据库。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.data.csv_importer import validate_csv_directory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--batch-id", required=True)
    args = parser.parse_args()
    report = validate_csv_directory(args.directory, args.batch_id)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    return 0 if report.ok else 2


if __name__ == "__main__":
    sys.exit(main())
