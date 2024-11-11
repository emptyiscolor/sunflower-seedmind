# Seed Generator 2
# Author: Wenxuan Shi <wenxuan.shi@northwestern.edu>
import logging

from seedgen2.utils.generators import SeedGeneratorStore
from seedgen2.utils.grpc import SeedD
# subgraphs
from seedgen2.agent.graphs.filetype import GRAPH_filetype
from seedgen2.agent.graphs.generate import GRAPH_generate


class SeedGenAgent:
    def __init__(self, result_dir: str, ip_addr: str, harness_binary: str):
        self.seedd = SeedD(ip_addr)
        self.result_dir = result_dir
        self.harness_binary = harness_binary

    def run(self):
        logging.info(f"Running SeedGen2 agent for harness binary: {
                     self.harness_binary}")
        # get functions in the harness binary
        functions = self.seedd.get_functions(self.harness_binary)

        store = SeedGeneratorStore()
        store.set_result_dir(self.result_dir)

        # TODO: locate the harness file (not implemented yet, need help from SeedD)
        # for now, we assume the harness file to be "/src/libxml2/fuzz/xml.c" ONLY for testing
        # and we use "get_region_source" to get the source code of the harness file
        # in the future, we should use "extract_function_source"
        harness_source_code = self.seedd.get_region_source(
            filepath="/src/libxml2/fuzz/xml.c",
            start_line=1,
            start_column=1,
            end_line=103,
            end_column=2,
        )

        # generate seeds with "filetype" subgraph (only run once)
        filetype_result = GRAPH_filetype(
            harness_source_code=harness_source_code,
            harness_file_name="xml.c",
            project_name="libxml2",
        )
        logging.info(f"Identified file type: {
                     filetype_result.get('file_type')}")
        logging.info(f"Identified features: {filetype_result.get('features')}")

        # generate seeds with "dictionary (string literal)" subgraph
        for feature in filetype_result.get("features"):
            generation_result = GRAPH_generate(
                harness_code=harness_source_code,
                file_type=filetype_result.get("file_type"),
                feature=feature,
            )
            logging.info(f"Generated seeds with feature: {feature}")

        # TODO: generate seeds with "code coverage" subgraph

        # TODO: generate seeds with "call relationship" subgraph
