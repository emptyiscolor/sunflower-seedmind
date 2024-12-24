from typing import Any
from seedgen2.utils.singleton import singleton
import os


@singleton
class Tracker:
    def __init__(self):
        self.log_id = 0

    def set_log_dir(self, log_dir: str):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_dir = os.path.abspath(self.log_dir)

    def add_trace(self, prompt: str, result: str, bot_name: str, additional_info: dict[str, Any]):
        trace_file_path = os.path.join(
            self.log_dir, f"trace_{self.log_id}_{bot_name}.txt")

        with open(trace_file_path, "w") as f:
            f.write("# PROMPT:\n")
            f.write(f"calling {bot_name} with prompt:\n")
            f.write(f"```\n{prompt}\n```\n\n")
            f.write("\n\n# RESULT:\n")
            f.write(f"```\n{result}\n```\n\n")
            f.write("\n")

            # Write each additional info with its key as section header
            for key, value in additional_info.items():
                f.write(f"\n## {key.upper()}:\n")
                f.write(f"```\n{str(value)}\n```\n\n")
                f.write("\n")

        self.log_id += 1
