#!/usr/bin/env python3
import sys
import json
import csv
from collections import defaultdict
from typing import Dict, List

DEFAULT_VALUE = 86400  # Default value if bug not triggered in an instance


def parse_json_data(json_file: str) -> Dict[str, Dict[str, List[int]]]:
    """
    Parse JSON file and group triggered values by fuzzer and bug ID.
    Collects all values across all harnesses for each bug.

    Returns:
        Dict mapping fuzzer_name -> bug_id -> list of all triggered values
    """
    with open(json_file, 'r') as f:
        data = json.load(f)

    # Structure: fuzzer -> bug_id -> list of all values
    fuzzer_data = defaultdict(lambda: defaultdict(list))

    results = data.get('results', {})

    for fuzzer_name, fuzzer_content in results.items():
        # Iterate through projects (openssl, libpng, etc.)
        for project_name, project_content in fuzzer_content.items():
            # Iterate through harnesses (server, client, etc.)
            for harness_name, harness_content in project_content.items():
                # Iterate through instances (0, 1, 2)
                for instance_id, instance_data in harness_content.items():
                    if not instance_id.isdigit():
                        continue

                    triggered = instance_data.get('triggered', {})

                    # Add each triggered bug value to the list
                    for bug_id, value in triggered.items():
                        fuzzer_data[fuzzer_name][bug_id].append(value)

    return fuzzer_data


def calculate_averages(fuzzer_data: Dict[str, Dict[str, List[int]]]) -> Dict[str, Dict[str, float]]:
    """
    Calculate average values for each fuzzer and bug ID.
    Pads values to the nearest multiple of 3 with DEFAULT_VALUE.

    Returns:
        Dict mapping fuzzer_name -> bug_id -> average_value
    """
    averages = {}

    for fuzzer_name, bugs in fuzzer_data.items():
        averages[fuzzer_name] = {}
        for bug_id, values in bugs.items():
            # Calculate how many padding values needed to reach next multiple of 3
            num_values = len(values)
            remainder = num_values % 3

            if remainder != 0:
                # Pad to next multiple of 3
                padding_needed = 3 - remainder
                values = values + [DEFAULT_VALUE] * padding_needed

            # Calculate average
            averages[fuzzer_name][bug_id] = sum(values) / len(values)

    return averages


def write_csv(averages: Dict[str, Dict[str, float]], output_file: str):
    """
    Write averages to CSV file.

    CSV format:
    bug_id, fuzzer1, fuzzer2, fuzzer3, ...
    """
    # Collect all unique bug IDs
    all_bug_ids = set()
    for fuzzer_bugs in averages.values():
        all_bug_ids.update(fuzzer_bugs.keys())

    # Sort bug IDs and fuzzer names for consistent output
    sorted_bug_ids = sorted(all_bug_ids)
    sorted_fuzzers = sorted(averages.keys())

    with open(output_file, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)

        # Write header
        header = ['bug_id'] + sorted_fuzzers
        writer.writerow(header)

        # Write data rows
        for bug_id in sorted_bug_ids:
            row = [bug_id]
            for fuzzer in sorted_fuzzers:
                value = averages[fuzzer].get(bug_id, DEFAULT_VALUE)
                row.append(f'{value:.2f}')
            writer.writerow(row)


def main():
    if len(sys.argv) != 3:
        print("Usage: count_by_fuzzers.py <input_json> <output_csv>", file=sys.stderr)
        sys.exit(1)

    input_json = sys.argv[1]
    output_csv = sys.argv[2]

    # Parse JSON and group by fuzzer
    fuzzer_data = parse_json_data(input_json)

    # Calculate averages
    averages = calculate_averages(fuzzer_data)

    # Write to CSV
    write_csv(averages, output_csv)

    print(f"Successfully processed {input_json} -> {output_csv}")


if __name__ == '__main__':
    main()
