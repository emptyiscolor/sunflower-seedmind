# Parse the GetCovID report
# GetCovID: https://github.com/whexy/GetCov

import re
import json
from dataclasses import dataclass
from typing import List, Optional

def parse_libfuzzer_log(log, levels):
    functions = []
    current_function = None

    for line in log.splitlines():
        line = line.strip()
        if line.startswith("COVERED_FUNC"):
            if current_function:
                functions.append(current_function)
            
            match = re.match(r"COVERED_FUNC: hits: (\d+) edges: (\d+)/(\d+) (.+) (?=\S+:\d+$)(.+):(\d+)", line)
            if match:
                hits, covered_edges, total_edges, func_name, file_path, line_number = match.groups()
                current_function = {
                    "name": func_name,
                    "hits": int(hits),
                    "covered_edges": int(covered_edges),
                    "total_edges": int(total_edges),
                    "location": f"{file_path}:{line_number}",
                    "fully_covered": int(covered_edges) == int(total_edges),
                    "uncovered_pcs": [],
                    "level": levels.get(func_name, float("inf"))
                }
        elif line.startswith("UNCOVERED_PC"):
            if current_function:
                match = re.match(r"UNCOVERED_PC: (.+):(\d+)", line)
                if match:
                    file_path, line_number = match.groups()
                    current_function["uncovered_pcs"].append(f"{file_path}:{line_number}")

    if current_function:
        functions.append(current_function)

    return functions


@dataclass
class PartiallyCoveredPredicate:
    file_path: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int
    true_count: int
    false_count: int

@dataclass
class CodeRegion:
    file_path: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int  # Exclusive

@dataclass
class PartiallyCoveredFunction:
    function_name: str
    file_path: str
    partially_covered_predicates: List[PartiallyCoveredPredicate]
    uncovered_regions: List[CodeRegion]
    whole_function: Optional[CodeRegion]

def parse_partially_covered_function(json_str: str) -> PartiallyCoveredFunction:
    """Parses a JSON representation of PartiallyCoveredFunction into a Python object."""
    data = json.loads(json_str)

    def parse_predicate(d: dict) -> PartiallyCoveredPredicate:
        return PartiallyCoveredPredicate(
            file_path=d['file_path'],
            start_line=d['start_line'],
            start_column=d['start_column'],
            end_line=d['end_line'],
            end_column=d['end_column'],
            true_count=d['true_count'],
            false_count=d['false_count'],
        )

    def parse_code_region(d: dict) -> CodeRegion:
        return CodeRegion(
            file_path=d['file_path'],
            start_line=d['start_line'],
            start_column=d['start_column'],
            end_line=d['end_line'],
            end_column=d['end_column'],
        )

    partially_covered_predicates = [
        parse_predicate(p) for p in data.get('partially_covered_predicates', [])
    ]

    uncovered_regions = [
        parse_code_region(r) for r in data.get('uncovered_regions', [])
    ]

    whole_function = (
        parse_code_region(data['whole_function']) if data.get('whole_function') else None
    )

    return PartiallyCoveredFunction(
        function_name=data['function_name'],
        file_path=data['file_path'],
        partially_covered_predicates=partially_covered_predicates,
        uncovered_regions=uncovered_regions,
        whole_function=whole_function,
    )
