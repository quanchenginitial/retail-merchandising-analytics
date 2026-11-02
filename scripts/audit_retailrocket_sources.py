"""Read-only Retailrocket v2 inventory audit; Python 3.11+ standard library.

Stream immutable CSVs without a database; publish only aggregate diagnostics.
Exact empty strings are missing. Property names/values are never stripped or cast.
Local hashes identify the supplied snapshot, not publisher-certified identity.
"""

import argparse
import csv
import hashlib
import json
import platform
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


SOURCE_PAGE = "https://www.kaggle.com/datasets/retailrocket/ecommerce-dataset"
METADATA_URL = "https://www.kaggle.com/api/v1/datasets/view/retailrocket/ecommerce-dataset"
FILE_LIST_URL = "https://www.kaggle.com/api/v1/datasets/list/retailrocket/ecommerce-dataset?datasetVersionNumber=2"
CONTRACT = {
    "events.csv": {
        "bytes": 94237913,
        "header": ["timestamp", "visitorid", "event", "itemid", "transactionid"],
        "integer_fields": ["visitorid", "itemid", "transactionid"],
        "optional_fields": ["transactionid"],
    },
    "item_properties_part1.csv": {
        "bytes": 484315749,
        "header": ["timestamp", "itemid", "property", "value"],
        "integer_fields": ["itemid"],
        "optional_fields": [],
    },
    "item_properties_part2.csv": {
        "bytes": 408929907,
        "header": ["timestamp", "itemid", "property", "value"],
        "integer_fields": ["itemid"],
        "optional_fields": [],
    },
    "category_tree.csv": {
        "bytes": 14454,
        "header": ["categoryid", "parentid"],
        "integer_fields": ["categoryid", "parentid"],
        "optional_fields": ["parentid"],
    },
}
EVENT_COUNTS = {"view": 2664312, "addtocart": 69332, "transaction": 22457}
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
MAX_UTC_MS = 253402300799999  # Last millisecond representable before UTC year 10000.


class SourceFormatError(ValueError):
    """Messages contain filenames/line numbers, never source field values."""


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def snapshot(path):
    before = path.stat()
    digest = sha256(path)
    after = path.stat()
    return {
        "size_bytes": after.st_size,
        "modified_time_ns": after.st_mtime_ns,
        "sha256": digest,
        "metadata_stable_during_hash": (before.st_size, before.st_mtime_ns)
        == (after.st_size, after.st_mtime_ns),
    }


def nonnegative_ascii_integer(value):
    # Reject signs, whitespace, decimal notation and Unicode digit lookalikes.
    return value.isascii() and value.isdecimal()


def utc_milliseconds(value):
    return (EPOCH + timedelta(milliseconds=value)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def scan_file(path, contract):
    started = time.perf_counter()
    header = contract["header"]
    optional = set(contract["optional_fields"])
    integer_indices = [(header.index(name), name) for name in contract["integer_fields"]]
    empty = dict.fromkeys(header, 0)
    invalid = dict.fromkeys(contract["integer_fields"], 0)
    event_counts = dict.fromkeys(EVENT_COUNTS, 0)
    unknown_events = 0
    transaction_empty = {event: 0 for event in EVENT_COUNTS}
    transaction_present = {event: 0 for event in EVENT_COUNTS}
    rows = invalid_timestamps = 0
    minimum = maximum = None
    has_timestamp = "timestamp" in header
    is_events = path.name == "events.csv"
    with path.open("rb") as raw:
        has_utf8_bom = raw.read(3) == b"\xef\xbb\xbf"
    try:
        # BOM is detected separately; decode all content strictly as UTF-8.
        with path.open("r", encoding="utf-8-sig", errors="strict", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            observed_header = next(reader, None)
            if observed_header != header:
                raise SourceFormatError(f"{path.name}: header mismatch")
            for row in reader:
                if len(row) != len(header):
                    raise SourceFormatError(f"{path.name}: field-count mismatch at physical line {reader.line_num}")
                rows += 1
                for index, name in enumerate(header):
                    empty[name] += row[index] == ""
                for index, name in integer_indices:
                    value = row[index]
                    invalid[name] += bool(value) and not nonnegative_ascii_integer(value)
                if has_timestamp:
                    value = row[0]
                    if value:
                        if not nonnegative_ascii_integer(value) or len(value) > 15:
                            invalid_timestamps += 1
                        else:
                            parsed = int(value)
                            if parsed > MAX_UTC_MS:
                                invalid_timestamps += 1
                            else:
                                minimum = parsed if minimum is None else min(minimum, parsed)
                                maximum = parsed if maximum is None else max(maximum, parsed)
                if is_events:
                    event = row[2]
                    if event in event_counts:
                        event_counts[event] += 1
                        transaction_empty[event] += row[4] == ""
                        transaction_present[event] += row[4] != ""
                    else:
                        unknown_events += 1
            physical_lines = reader.line_num
    except (UnicodeError, csv.Error) as exc:
        # Parser exception text can contain source content; deliberately suppress it.
        raise SourceFormatError(f"{path.name}: {type(exc).__name__}; complete strict parse failed") from None
    checks = {
        "complete_utf8_strict_csv_parse": True,
        "exact_header": True,
        "all_record_widths_match_header": True,
        "required_fields_present": all(empty[name] == 0 for name in header if name not in optional),
        "nonempty_identifier_fields_are_nonnegative_ascii_integers": not any(invalid.values()),
    }
    result = {
        "rows": rows,
        "csv_records_including_header": rows + 1,
        "physical_lines_including_header": physical_lines,
        "columns": len(header),
        "column_names": observed_header,
        "encoding": "UTF-8 (strict decoding; optional BOM removed only for parsing)",
        "utf8_bom_present": has_utf8_bom,
        "empty_fields": empty,
        "expected_optional_fields": sorted(optional),
        "invalid_nonempty_identifier_fields": invalid,
        "checks": checks,
    }
    if has_timestamp:
        result["timestamp"] = {
            "unit": "Unix milliseconds", "invalid_nonempty_values": invalid_timestamps,
            "min_unix_ms": minimum, "max_unix_ms": maximum,
            "min_utc": utc_milliseconds(minimum) if minimum is not None else None,
            "max_utc": utc_milliseconds(maximum) if maximum is not None else None,
        }
        checks["nonempty_timestamps_are_nonnegative_integer_milliseconds_in_utc_range"] = invalid_timestamps == 0
    if is_events:
        result.update({"event_counts": event_counts, "unknown_event_rows": unknown_events,
                       "empty_transactionid_by_event": transaction_empty,
                       "present_transactionid_by_event": transaction_present})
        checks.update({"published_event_count_matches": rows == 2756101,
                       "published_event_type_counts_match": event_counts == EVENT_COUNTS,
                       "only_documented_event_types": unknown_events == 0,
                       "transaction_events_have_transactionid": transaction_empty["transaction"] == 0,
                       "nontransaction_events_have_empty_transactionid": transaction_present["view"] + transaction_present["addtocart"] == 0})
    if path.name == "category_tree.csv":
        checks["published_category_row_count_matches"] = rows == 1669
    result["scan_seconds"] = round(time.perf_counter() - started, 3)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source_dir.resolve()
    output = args.output.resolve()
    if output == source or source in output.parents:
        parser.error("The output must be outside the immutable source directory")
    csv.field_size_limit(2**31 - 1)  # Fits Windows C long; never truncate long text.
    paths = {name: source / name for name in CONTRACT}
    if not all(path.is_file() for path in paths.values()):
        parser.error("All four expected source CSVs must be present")
    started = time.perf_counter()
    report = {
        "audit_started_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "scope": "Assistant read-only streaming source inventory; no database, deduplication, joins or business analytics.",
        "acquisition": "User reported downloading four extracted files to D:/database/retailrocket on 2026-11-02; exact download time/channel and archive hash were not captured by this audit.",
        "source_page": SOURCE_PAGE, "metadata_url": METADATA_URL, "file_list_url": FILE_LIST_URL,
        "publisher_metadata_checked_on": "2026-11-02", "selected_version": 2,
        "publisher_expected_bytes": {name: spec["bytes"] for name, spec in CONTRACT.items()},
        "publisher_checksums_available": False,
        "checksum_provenance": "Observed local SHA-256 only; no verified publisher checksum was available. Matching length is not proof of official byte identity.",
        "missingness_definition": "Only the exact empty string; no whitespace stripping, imputation or property-value conversion.",
        "files": {}, "checks": {},
        "not_checked": ["unique visitors/items/orders", "duplicate rows or key uniqueness", "category relationships/cycles", "event-to-property coverage", "time-aware attribute joins", "sessions/RF/funnels/baskets", "publisher byte identity or download provenance"],
    }
    before = {name: snapshot(path) for name, path in paths.items()}
    for name, path in paths.items():
        try:
            report["files"][name] = scan_file(path, CONTRACT[name])
            print(f"Scanned {name}: {report['files'][name]['rows']:,} data rows", flush=True)
        except SourceFormatError as exc:
            report["files"][name] = {"parse_error": str(exc), "checks": {"complete_utf8_strict_csv_parse": False}}
            print(f"Parse failed for {name}; no source values logged", flush=True)
    after = {name: snapshot(path) for name, path in paths.items()}
    report["source_before"] = before
    report["source_after"] = after
    for name, result in report["files"].items():
        result.update({"size_bytes": before[name]["size_bytes"], "sha256": before[name]["sha256"]})
        result["checks"].update({
            "publisher_expected_byte_count_matches": before[name]["size_bytes"] == CONTRACT[name]["bytes"],
            "source_hash_and_metadata_unchanged": before[name] == after[name] and before[name]["metadata_stable_during_hash"],
        })
    report["checks"]["published_combined_property_row_count_matches"] = sum(
        report["files"][name].get("rows", 0) for name in ("item_properties_part1.csv", "item_properties_part2.csv")
    ) == 20275902
    all_checks = list(report["checks"].values()) + [v for result in report["files"].values() for v in result["checks"].values()]
    report.update({"checks_passed": sum(all_checks), "checks_total": len(all_checks),
                   "all_checks_passed": all(all_checks),
                   "audit_completed_utc": datetime.now(timezone.utc).isoformat(),
                   "elapsed_seconds": round(time.perf_counter() - started, 3),
                   "audit_script_sha256": sha256(Path(__file__))})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"all_checks_passed": report["all_checks_passed"], "checks_passed": report["checks_passed"],
                      "checks_total": report["checks_total"], "elapsed_seconds": report["elapsed_seconds"]}))
    return 0 if report["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
