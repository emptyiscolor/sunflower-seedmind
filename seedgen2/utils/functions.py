# Get function information from SeedD runtime

from dataclasses import dataclass
from typing import List
import json

@dataclass
class FunctionInfo:
    name: str
    file_path: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int

def parse_functions(json_str: str) -> List[FunctionInfo]:
    response = json.loads(json_str)
    return [FunctionInfo(**fi) for fi in response]
