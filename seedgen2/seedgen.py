# Seed Generator 2
# Author: Wenxuan Shi <wenxuan.shi@northwestern.edu>
from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path

from seedgen2.agent.graphs.filetype import generate_based_on_filetype, get_filetype
from seedgen2.agent.graphs.predicates import improve_entrance_by_predicate
from seedgen2.agent.sowbot import SowbotResult
from seedgen2.utils.grpc import SeedD
from seedgen2.utils.generators import SeedGeneratorStore
from seedgen2.utils.functions import get_functions, FunctionInfo

import logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')


@dataclass
class HarnessInfo:
    """Contains information about the harness file."""
    file_path: str
    source_code: str
    file_name: str


class SeedGenAgent:
    """Agent responsible for generating seeds based on various strategies."""

    def __init__(self, result_dir: str, ip_addr: str, project_name: str, harness_binary: str):
        """Initialize the SeedGenAgent.

        Args:
            result_dir: Directory to store results
            ip_addr: IP address for SeedD service
            project_name: Name of the project
            harness_binary: Path to the harness binary
        """
        self.seedd = SeedD(ip_addr, shared_dir=f"{result_dir}/shared")
        self.result_dir = Path(result_dir)
        self.project_name = project_name
        self.harness_binary = harness_binary
        self.store = SeedGeneratorStore()
        self.store.set_result_dir(result_dir)

    def _find_harness_function(self, functions: List[FunctionInfo]) -> Optional[FunctionInfo]:
        return next(
            (func for func in functions if "LLVMFuzzerTestOneInput" in func.name),
            None
        )

    def _get_harness_info(self, functions: List[FunctionInfo]) -> HarnessInfo:
        harness_func = self._find_harness_function(functions)
        if not harness_func:
            raise ValueError(
                "Failed to locate the harness file. No function named 'LLVMFuzzerTestOneInput' found."
            )

        logging.info(f"Located harness file: {harness_func.file_path}")

        source_code = self.seedd.get_region_source(
            filepath=harness_func.file_path,
            start_line=0, start_column=0,
            end_line=0, end_column=0
        ).source

        return HarnessInfo(
            file_path=harness_func.file_path,
            source_code=source_code,
            file_name=Path(harness_func.file_path).name
        )

    def _generate_filetype_seeds(self, harness_info: HarnessInfo) -> SowbotResult:
        filetype_result = get_filetype(
            harness_source_code=harness_info.source_code,
            harness_file_name=harness_info.file_name,
            project_name=self.project_name,
        )

        logging.info(f"Identified file type: {filetype_result.file_type}")
        logging.info(f"Identified features: {filetype_result.features}")

        result = generate_based_on_filetype(
            self.seedd,
            self.harness_binary,
            harness_info.source_code,
            filetype_result
        )
        return result

    def run(self) -> None:
        """Run the seed generation process."""
        logging.info(f"Running SeedGen2 agent for harness binary: {
                     self.harness_binary}")

        # Get functions and harness information
        functions = get_functions(self.seedd, self.harness_binary)
        harness_info = self._get_harness_info(functions)

        # Generate seeds using different strategies
        result = self._generate_filetype_seeds(harness_info)
        improve_entrance_by_predicate(
            self.seedd, result.generator_script, result.seed_evaluation_result, functions, self.harness_binary)

        # TODO: generate seeds with "dictionary (string literal)" subgraph
        # TODO: generate seeds with "code coverage" subgraph
        # TODO: generate seeds with "call relationship" subgraph
