#!/usr/bin/env python3
import sys
import csv
from collections import defaultdict
from typing import Dict, List, Tuple
import os


# Mapping from filename keywords to display names
SETTING_NAME_MAP = {
    'empty': 'NONE',
    'default': 'DEFAULT',
    'seedmind': 'SEEDMIND',
    'mini': 'OSSFuzz-AI',
    'ossfuzzai': 'OSSFuzz-AI',
}


def parse_csv_file(csv_file: str) -> Tuple[str, Dict[str, Dict[str, float]]]:
    """
    Parse a CSV file and extract bug data.

    Returns:
        Tuple of (setting_name, dict mapping bug_id -> fuzzer_name -> value)
    """
    # Extract setting name from filename (e.g., "output_seedmind.csv" -> "SEEDMIND")
    basename = os.path.basename(csv_file)
    # Remove "output_" prefix and ".csv" suffix
    setting_key = basename.replace('output_', '').replace('.csv', '').lower()

    # Map to display name
    setting_name = SETTING_NAME_MAP.get(setting_key, setting_key.upper())

    bug_data = defaultdict(dict)

    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            bug_id = row['bug_id']
            for fuzzer_name, value_str in row.items():
                if fuzzer_name != 'bug_id':
                    bug_data[bug_id][fuzzer_name] = float(value_str)

    return setting_name, bug_data


def seconds_to_human_readable(seconds: float) -> str:
    """
    Convert seconds to human-readable format.

    Returns format like: 1d, 2h, 3m, 4s
    If >= 86400 (24 hours), return "-"
    """
    if seconds >= 86400:
        return "-"

    # Round to nearest second
    seconds = int(round(seconds))

    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if days > 0:
        return f"{days}d"
    elif hours > 0:
        return f"{hours}h"
    elif minutes > 0:
        return f"{minutes}m"
    else:
        return f"{secs}s"


def merge_csv_files(csv_files: List[str], output_file: str):
    """
    Merge multiple CSV files and create formatted output.
    """
    # Parse all CSV files
    all_data = {}  # setting_name -> bug_id -> fuzzer_name -> value
    all_bug_ids = set()
    all_fuzzers = set()

    for csv_file in csv_files:
        setting_name, bug_data = parse_csv_file(csv_file)
        all_data[setting_name] = bug_data

        for bug_id, fuzzer_values in bug_data.items():
            all_bug_ids.add(bug_id)
            all_fuzzers.update(fuzzer_values.keys())

    # Sort bug IDs, fuzzer names (reverse order for AFL++, HONGGFUZZ, AFL), and settings
    sorted_bug_ids = sorted(all_bug_ids)
    # Reverse sort fuzzers so AFL++ comes first, then HONGGFUZZ, then AFL
    sorted_fuzzers = sorted(all_fuzzers, reverse=True)
    sorted_settings = sorted(all_data.keys())

    # Write merged CSV
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)

        # Write header row with fuzzer names spanning multiple columns
        header = ['BUG ID']
        for fuzzer in sorted_fuzzers:
            header.append(fuzzer.upper())
            header.extend([''] * (len(sorted_settings) - 1))
        writer.writerow(header)

        # Write subheader with setting names
        subheader = ['']
        for fuzzer in sorted_fuzzers:
            subheader.extend(sorted_settings)
        writer.writerow(subheader)

        # Write data rows
        for bug_id in sorted_bug_ids:
            row = [bug_id]

            for fuzzer in sorted_fuzzers:
                for setting in sorted_settings:
                    value = all_data.get(setting, {}).get(
                        bug_id, {}).get(fuzzer, 86400.0)
                    row.append(seconds_to_human_readable(value))

            writer.writerow(row)


def main():
    if len(sys.argv) < 3:
        print("Usage: merge_results.py <output.csv> <input1.csv> <input2.csv> ...", file=sys.stderr)
        print("", file=sys.stderr)
        print("Example: merge_results.py merged.csv output_empty.csv output_mini.csv output_seedmind.csv", file=sys.stderr)
        print("", file=sys.stderr)
        print("Filename mappings:", file=sys.stderr)
        for key, value in sorted(SETTING_NAME_MAP.items()):
            print(f"  output_{key}.csv -> {value}", file=sys.stderr)
        sys.exit(1)

    output_file = sys.argv[1]
    input_files = sys.argv[2:]

    # Verify all input files exist
    for input_file in input_files:
        if not os.path.exists(input_file):
            print(
                f"Error: Input file not found: {input_file}", file=sys.stderr)
            sys.exit(1)

    merge_csv_files(input_files, output_file)

    print(f"Successfully merged {len(input_files)} files -> {output_file}")
    print(
        f"Input files: {', '.join([os.path.basename(f) for f in input_files])}")


if __name__ == '__main__':
    main()
