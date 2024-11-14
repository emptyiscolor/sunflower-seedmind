# LLM will generate seed "generators", which is actually a python program.
# This module is used to store, manage, and execute these generators.

import os
import subprocess
from seedgen2.utils.singleton import singleton
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class GeneratorRunResult:
    success: bool
    error_message: Optional[str]
    seed_paths: Optional[List[str]]

    def get_seed_paths(self) -> Optional[List[str]]:
        return self.seed_paths

    def is_success(self) -> bool:
        return self.success

    def get_error_message(self) -> Optional[str]:
        return self.error_message


@singleton
class SeedGeneratorStore:
    def __init__(self):
        self.result_dir = ""
        self.generators: list[str] = []
        self.num_seeds = 100

    def set_result_dir(self, result_dir: str):
        self.result_dir = result_dir
        os.makedirs(self.result_dir, exist_ok=True)
        # make sure the result dir is absolute path, because we will use it in Docker mount
        self.result_dir = os.path.abspath(self.result_dir)

    def set_num_seeds(self, num_seeds: int):
        self.num_seeds = num_seeds

    def get_generator(self, generator_id: int) -> str:
        return self.generators[generator_id]

    def new_generator(self, generator_source_code: str) -> int:
        if self.result_dir == "":
            raise ValueError(
                "Result directory is not set yet. Please make sure to use `set_result_dir` at lease once before submit new generator!")

        self.generators.append(generator_source_code)
        return len(self.generators) - 1

    def run_generator(self, generator_id: int) -> GeneratorRunResult:
        # Write the generator source code to result_dir
        generator_file_path = os.path.join(
            self.result_dir, f"generator_{generator_id}.py")
        wrapper_file_path = os.path.join(
            self.result_dir, f"wrapper_{generator_id}.sh")

        # Create a shell wrapper that runs the generator n times
        wrapper_code = f'''#!/bin/sh
for i in $(seq 0 {self.num_seeds - 1})
do
    python /app/generator.py "/app/output/seed_{generator_id}_$i"
    if [ $? -ne 0 ]; then
        echo "Generator failed at iteration $i"
        exit 1
    fi
done
'''
        # Write both scripts
        with open(generator_file_path, "w") as f:
            f.write(self.generators[generator_id])
        with open(wrapper_file_path, "w") as f:
            f.write(wrapper_code)
        # Make the wrapper executable
        os.chmod(wrapper_file_path, 0o755)

        # Create seeds directory
        seeds_dir = os.path.join(self.result_dir, "seeds")
        os.makedirs(seeds_dir, exist_ok=True)

        # Prepare the list of expected seed paths
        seed_paths = [
            os.path.join(seeds_dir, f"seed_{generator_id}_{i}")
            for i in range(self.num_seeds)
        ]

        # Run the wrapper script in Docker container
        docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{generator_file_path}:/app/generator.py:ro",
            "-v", f"{wrapper_file_path}:/app/wrapper.sh:ro",
            "-v", f"{seeds_dir}:/app/output",
            "python:3.9-slim",
            "/app/wrapper.sh"
        ]

        result = subprocess.run(docker_cmd, stderr=subprocess.PIPE)
        if result.returncode != 0:
            return GeneratorRunResult(False, result.stderr.decode("utf-8"), None)

        # Check if all seed files exist
        missing_files = [p for p in seed_paths if not os.path.exists(p)]
        if missing_files:
            return GeneratorRunResult(
                False,
                f"The generator exited normally, but some seed files are missing: {
                    missing_files}",
                None
            )

        return GeneratorRunResult(True, None, seed_paths)
