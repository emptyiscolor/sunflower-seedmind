# Seed Generator 2
# Author: Wenxuan Shi <wenxuan.shi@northwestern.edu>
import logging

from seedgen2.utils.functions import get_functions
from seedgen2.utils.generators import SeedGeneratorStore
from seedgen2.utils.grpc import SeedD
# subgraphs
from seedgen2.agent.graphs.filetype import GRAPH_filetype
from seedgen2.agent.graphs.generate import GRAPH_generate


class SeedGenAgent:
    def __init__(self, result_dir: str, ip_addr: str, project_name: str, harness_binary: str):
        self.seedd = SeedD(ip_addr)
        self.result_dir = result_dir
        self.project_name = project_name
        self.harness_binary = harness_binary

    def run(self):
        logging.info(f"Running SeedGen2 agent for harness binary: {
                     self.harness_binary}")
        # get functions in the harness binary
        functions = get_functions(self.seedd, self.harness_binary)

        store = SeedGeneratorStore()
        store.set_result_dir(self.result_dir)

        # locate the harness file (not implemented yet, need help from SeedD)
        # Search "LLVMFuzzerTestOneInput" in the functions
        harness_file_path = None
        for function in functions:
            if "LLVMFuzzerTestOneInput" in function.name:
                harness_file_path = function.file_path
                break
        if harness_file_path is None:
            raise ValueError("Failed to locate the harness file. No function named "
                             "'LLVMFuzzerTestOneInput' found.")
        logging.info(f"Located harness file: {harness_file_path}")

        # Get the source code of the harness file
        harness_source_code = self.seedd.get_region_source(
            filepath=harness_file_path,
            start_line=0,
            start_column=0,
            end_line=0,
            end_column=0,
        )  # set all to 0 to get the whole file (it's a hidden feature!)

        # generate seeds with "filetype" subgraph (only run once)
        harness_file_name = harness_file_path.split("/")[-1]
        filetype_result = GRAPH_filetype(
            harness_source_code=harness_source_code,
            harness_file_name=harness_file_name,
            project_name=self.project_name,
        )
        logging.info(f"Identified file type: {
                     filetype_result.get('file_type')}")
        logging.info(f"Identified features: {filetype_result.get('features')}")

        for feature in filetype_result.get("features"):
            generation_result = GRAPH_generate(
                harness_code=harness_source_code,
                file_type=filetype_result.get("file_type"),
                feature=feature,
            )
            logging.info(f"Generated seeds with feature: {feature}")
        
        # TODO: generate seeds with "dictionary (string literal)" subgraph

        # TODO: generate seeds with "code coverage" subgraph

        # TODO: generate seeds with "call relationship" subgraph
