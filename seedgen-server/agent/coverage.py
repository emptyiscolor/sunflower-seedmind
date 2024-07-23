import os
import subprocess
from typing import List, Dict, Optional


class CoverageCenter:
    def __init__(self, storage_path: str, mapped_path: str):
        self.storage_path = storage_path
        self.mapped_path = mapped_path
        os.makedirs(self.storage_path, exist_ok=True)
        os.makedirs(os.path.join(self.storage_path, "generators"), exist_ok=True)
        os.makedirs(os.path.join(self.storage_path, "seeds"), exist_ok=True)
        self.coverage_data = {}

    def store_script(self, script_id: int, script: str) -> str:
        script_path = os.path.join(
            self.storage_path, "generators", f"generator{script_id}.py"
        )
        with open(script_path, "w") as f:
            f.write(script)
        self.coverage_data[script_id] = {
            "script": script,
            "coverage": None,
            "evaluation": None,
        }
        return script_path

    def generate_seeds(self, script_path: str, num_seeds: int = 50, timeout: int = 1) -> List[str]:
        seed_files = []
        seed_id_start = len(os.listdir(os.path.join(self.storage_path, "seeds")))
        for seed_id in range(seed_id_start, seed_id_start + num_seeds):
            seed_file = os.path.join(self.storage_path, "seeds", f"seed{seed_id}")
            try:
                subprocess.run(
                    ["python3", script_path, seed_file],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=timeout,
                )
                mapped_seed_file = f"{self.mapped_path}/seeds/seed{seed_id}"
                seed_files.append(mapped_seed_file)
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"Error running the generator script: {e.stderr}")
        return seed_files

    def store_coverage_info(self, script_id: int, coverage: str):
        self.coverage_data[script_id]["coverage"] = coverage

    def store_evaluation(self, script_id: int, evaluation: str):
        self.coverage_data[script_id]["evaluation"] = evaluation

    def get_info(self, script_id: int) -> Dict[str, Optional[str]]:
        # return (script, coverage, evaluation)
        if script_id not in self.coverage_data:
            return None
        return self.coverage_data[script_id]