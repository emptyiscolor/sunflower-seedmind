# parse the libFuzzer print_coverage output

# 1. ignore uncovered_func
# 2. collect all covered_func
# 3. for each covered_func, collect uncovered_edge

import re
from collections import defaultdict

def parse_libfuzzer_log(log, levels):
    functions = []
    current_function = None

    for line in log.splitlines():
        line = line.strip()
        if line.startswith("COVERED_FUNC"):
            if current_function:
                functions.append(current_function)
            
            match = re.match(r"COVERED_FUNC: hits: (\d+) edges: (\d+)/(\d+) (\S+) (.+):(\d+)", line)
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
