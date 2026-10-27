"""Read-only M5 source audit; Python 3.11+ standard library, no database required.

Usage: python scripts/audit_m5_sources.py --source-dir PATH --output PATH
Source records are never written to the report. Files are hashed before and after.
"""

import argparse
import csv
import hashlib
import json
import platform
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path


FILES = ("calendar.csv", "sales_train_evaluation.csv", "sell_prices.csv")
CALENDAR = "date wm_yr_wk weekday wday month year d event_name_1 event_type_1 event_name_2 event_type_2 snap_CA snap_TX snap_WI".split()
IDENTIFIERS = "id item_id dept_id cat_id store_id state_id".split()
SALES = IDENTIFIERS + [f"d_{i}" for i in range(1, 1942)]
PRICES = "store_id item_id wm_yr_wk sell_price".split()


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def rows(path, expected):
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        header = next(reader)
        if header != expected:
            raise ValueError(f"{path.name}: header does not match the selected M5 contract")
        for line_number, row in enumerate(reader, 2):
            if len(row) != len(expected):
                raise ValueError(f"{path.name}:{line_number}: incorrect field count")
            yield row


def audit_calendar(path):
    records = list(rows(path, CALENDAR))
    dates = [date.fromisoformat(row[0]) for row in records]
    day_numbers = [int(row[6].removeprefix("d_")) for row in records]
    checks = {
        "expected_row_count": len(records) == 1969,
        "unique_dates": len(set(dates)) == len(dates),
        "unique_day_ids": len(set(day_numbers)) == len(records),
        "continuous_dates": dates == [date(2011, 1, 29) + timedelta(days=i) for i in range(len(records))],
        "continuous_day_labels": [row[6] for row in records] == [f"d_{i}" for i in range(1, len(records) + 1)],
        "core_fields_present": all(all(row[i] != "" for i in [0, 1, 2, 3, 4, 5, 6, 11, 12, 13]) for row in records),
        "calendar_attributes_match": all(row[2] == d.strftime("%A") and int(row[3]) == (d.weekday() + 2) % 7 + 1 and int(row[4]) == d.month and int(row[5]) == d.year for row, d in zip(records, dates)),
        "snap_is_binary": all(row[i] in ("0", "1") for row in records for i in (11, 12, 13)),
        "event_missingness_paired": all((row[7] == "") == (row[8] == "") and (row[9] == "") == (row[10] == "") for row in records),
    }
    result = {
        "rows": len(records), "columns": len(CALENDAR), "column_names": CALENDAR,
        "date_min": str(min(dates)), "date_max": str(max(dates)),
        "unique_weeks": len({row[1] for row in records}),
        "empty_fields": {c: sum(row[i] == "" for row in records) for i, c in enumerate(CALENDAR)},
        "selected_dates": {row[6]: row[0] for row in records if row[6] in {"d_1829", "d_1857", "d_1885", "d_1913", "d_1941", "d_1969"}},
        "checks": checks,
    }
    return result, records


def audit_sales(path):
    ids, pairs, products, stores = set(), set(), {}, {}
    counts, totals_by_store = Counter(), Counter()
    departments, categories, states = set(), set(), set()
    max_units = 0
    for row in rows(path, SALES):
        counts["rows"] += 1
        sid, item, dept, cat, store, state = row[:6]
        counts["missing_identifier_cells"] += sum(value == "" for value in row[:6])
        counts["duplicate_ids"] += sid in ids
        counts["duplicate_item_store_keys"] += (item, store) in pairs
        counts["id_label_mismatches"] += sid != f"{item}_{store}_evaluation"
        counts["inconsistent_product_mapping_rows"] += item in products and products[item] != (dept, cat)
        counts["inconsistent_store_mapping_rows"] += store in stores and stores[store] != state
        ids.add(sid)
        pairs.add((item, store))
        products[item], stores[store] = (dept, cat), state
        departments.add(dept)
        categories.add(cat)
        states.add(state)
        # Parse each value explicitly; missing/invalid values are counted, never filled.
        units = []
        for value in row[6:]:
            if value == "":
                counts["missing_sales_cells"] += 1
                continue
            try:
                parsed = int(value)
            except ValueError:
                counts["invalid_integer_sales_cells"] += 1
                continue
            units.append(parsed)
        counts["valid_integer_sales_cells"] += len(units)
        counts["negative_sales_cells"] += sum(value < 0 for value in units)
        counts["zero_sales_cells"] += units.count(0)
        row_units = sum(units)
        counts["total_units"] += row_units
        totals_by_store[store] += row_units
        max_units = max(max_units, max(units, default=0))
    for key in ["missing_identifier_cells", "duplicate_ids", "duplicate_item_store_keys", "id_label_mismatches", "inconsistent_product_mapping_rows", "inconsistent_store_mapping_rows", "missing_sales_cells", "invalid_integer_sales_cells", "negative_sales_cells"]:
        counts.setdefault(key, 0)
    issues = [key for key in counts if key.startswith(("missing_", "duplicate_", "invalid_", "negative_", "inconsistent_", "id_label_"))]
    checks = {key + "_zero": counts[key] == 0 for key in issues}
    checks.update({"expected_rows": counts["rows"] == 30490, "expected_products": len(products) == 3049, "expected_stores": len(stores) == 10, "expected_states": len(states) == 3, "expected_sales_cells": counts["valid_integer_sales_cells"] == 59181090})
    return {
        **dict(counts), "columns": len(SALES), "identifier_columns": IDENTIFIERS,
        "day_columns": {"first": "d_1", "last": "d_1941", "count": 1941},
        "products": len(products), "stores": len(stores), "states": len(states),
        "departments": len(departments), "categories": len(categories),
        "max_daily_units": max_units, "control_units_by_store": dict(sorted(totals_by_store.items())),
        "checks": checks,
    }, pairs


def audit_prices(path, sales_pairs, calendar_records):
    week_index = {week: i for i, week in enumerate(sorted({r[1] for r in calendar_records}))}
    seen = defaultdict(int)
    pair_set, week_set = set(), set()
    counts, nulls = Counter(), Counter()
    min_price = max_price = None
    for row in rows(path, PRICES):
        counts["rows"] += 1
        store, item, week, price = row
        pair = (item, store)
        pair_set.add(pair)
        week_set.add(week)
        for name, value in zip(PRICES, row):
            nulls[name] += value == ""
        counts["orphan_item_store_rows"] += pair not in sales_pairs
        if week not in week_index:
            counts["unknown_calendar_week_rows"] += 1
        else:
            bit = 1 << week_index[week]
            counts["duplicate_composite_keys"] += bool(seen[pair] & bit)
            seen[pair] |= bit
        try:
            number = Decimal(price)
            if not number.is_finite():
                raise InvalidOperation
            counts["nonpositive_price_rows"] += number <= 0
            min_price = number if min_price is None else min(min_price, number)
            max_price = number if max_price is None else max(max_price, number)
        except InvalidOperation:
            counts["invalid_numeric_price_rows"] += 1
    for key in ["orphan_item_store_rows", "unknown_calendar_week_rows", "duplicate_composite_keys", "nonpositive_price_rows", "invalid_numeric_price_rows"]:
        counts.setdefault(key, 0)
    checks = {key + "_zero": counts[key] == 0 for key in counts if key != "rows"}
    checks.update({"all_fields_present": sum(nulls.values()) == 0, "all_sales_pairs_have_some_price": pair_set == sales_pairs})
    return {
        **dict(counts), "columns": len(PRICES), "column_names": PRICES,
        "empty_fields": dict(nulls), "item_store_pairs": len(pair_set),
        "weeks": len(week_set), "week_min": min(week_set), "week_max": max(week_set),
        "price_min": str(min_price), "price_max": str(max_price), "checks": checks,
        "not_checked": ["day-level price coverage for positive sales", "financial meaning or realised transaction prices"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    paths = {name: args.source_dir / name for name in FILES}
    if args.output.resolve() in {p.resolve() for p in paths.values()}:
        raise ValueError("Output must not overwrite a source file")
    before = {name: {"size_bytes": p.stat().st_size, "sha256": sha256(p)} for name, p in paths.items()}
    calendar, records = audit_calendar(paths[FILES[0]])
    print("Calendar scan complete", flush=True)
    sales, pairs = audit_sales(paths[FILES[1]])
    print("Sales scan complete", flush=True)
    prices = audit_prices(paths[FILES[2]], pairs, records)
    print("Price scan complete", flush=True)
    outputs = {FILES[0]: calendar, FILES[1]: sales, FILES[2]: prices}
    for name, result in outputs.items():
        result.update(before[name])
        result["checks"]["source_hash_unchanged_during_audit"] = sha256(paths[name]) == before[name]["sha256"]
    checks = [passed for result in outputs.values() for passed in result["checks"].values()]
    report = {
        "audit_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "scope": "Assistant read-only source-file audit; no persistent project database, SQL mart or learner execution.",
        "acquisition": "User supplied files and reported completing the M5 download on 2026-10-27; exact retrieval time, download URL and archive hash were not captured.",
        "source_page": "https://www.kaggle.com/competitions/m5-forecasting-accuracy/data",
        "files": outputs, "checks_passed": sum(checks), "checks_total": len(checks),
        "all_checks_passed": all(checks),
        "limits": ["Local hashes identify this snapshot; no publisher checksum was available for comparison.", "Full source-to-database reconciliation and day-level price coverage remain pending.", "Zero unit sales do not establish stockouts or zero demand."],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"checks_passed": sum(checks), "checks_total": len(checks), "rows": {k: v["rows"] for k, v in outputs.items()}}))
    if not all(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
