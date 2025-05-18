# Seed Generator wiht MCP adaptors
# Only relies on the harness source code, without SeedD and getcov
from pathlib import Path

from seedgen2.agents.alignment import align_script, update_doc_mini
from seedgen2.agents.filetype import generate_based_on_filetype, get_filetype, generate_reference_script
from seedgen2.agents.glance import generate_first_script
from seedgen2.utils.generators import SeedGeneratorStore
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from typing import Any, Dict

from seedgen2.presets import SeedGen2GenerativeModel

import logging
import os

from seedgen2.utils.tracker import Tracker
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')


class CodeAnalysisAgent:
    """Agent responsible for code analysis and planner.
    Note: Use a separate agent for code analysis as the code base consumes too many tokens.
    """

    def __init__(self):
        self.client = MultiServerMCPClient(
            {
                "filesystem": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem"],
                    "transport": "stdio",
                },
                "treesitter": {
                    "command": "python3",
                    "args": ["-m", "mcp_server_tree_sitter.server"],
                    "transport": "stdio",
                }
            }
        )
        self.agent = None

    async def setup_analysis_agent_react(self, model_name: str = "openai:gpt-4o") -> Any:
        """Set up the react agent."""
        tools = await self.client.get_tools()
        self.agent = create_react_agent(model_name, tools)
        # TODO: mcp_response = await agent.ainvoke({"messages": "Show me the coding plan on how to write the Python functions to prepare parts of the input for all the required data structures"})

    async def setup_analysis_agent_stateful(self, model_name: str = "openai:gpt-4o") -> Any:
        """Set up LangGraph StateGraph."""
        # builder = StateGraph(MessagesState)
        # builder.add_node(call_model)
        # builder.add_node(ToolNode(tools))
        # builder.add_edge(START, "call_model")
        # builder.add_conditional_edges(
        #     "call_model",
        #     tools_condition,
        # )
        # builder.add_edge("tools", "call_model")
        # graph = builder.compile()
        pass


class SeedMcpAgent:
    """Agent responsible for generating seeds based on various strategies."""

    def __init__(self, result_dir: str, src_dir: str, project_name: str, harness_binary: str, harness_source: str, gen_model: str):
        """Initialize the SeedGenAgent.

        Args:
            result_dir: Directory to store results
            project_name: Name of the project
            harness_binary: Path to the harness binary
            harness_source: Source code of the harness binary
        """
        self.shared_dir = Path(f"{result_dir}/../shared")
        self.result_dir = Path(result_dir)
        self.src_dir = Path(src_dir)
        self.project_name = project_name
        self.harness_binary = harness_binary
        self.harness_source = harness_source
        self.store = SeedGeneratorStore()
        self.store.set_result_dir(result_dir)
        self.tracker = Tracker()
        self.tracker.set_log_dir(result_dir)
        SeedGen2GenerativeModel.set_custom_model(gen_model)

    def run(self) -> None:
        """Run the seed generation process."""
        logging.info(f"Running SeedGen2 MCP agent for harness binary: {
                     self.harness_binary}")

        # Seed generation pipeline

        # 1. Generate 3 ingredients: initial generator script, structure documentation, and target filetype
        current_result = generate_first_script(
            None, self.harness_source, self.harness_binary)
        current_script = current_result.generator_script
        current_doc = update_doc_mini(self.harness_source, self.harness_binary)
        filetype_result = get_filetype(
            harness_source_code=self.harness_source,
            harness_file_name=self.harness_binary,
            project_name=self.project_name,
        )
        filetype_result = filetype_result.translate(
            str.maketrans('', '', "\"'`"))  # remove quotes and ticks

        # 2. Generate the complete generator script
        if filetype_result == "unknown":
            logging.info(
                f"Unknown filetype, only using structure information for generation")
            current_result = align_script(
                None, current_script, current_doc, self.harness_binary)
        else:
            logging.info(f"Generating seeds for filetype {filetype_result}")
            reference_script = generate_reference_script(
                None, self.harness_binary, filetype_result)
            current_result = generate_based_on_filetype(
                None,
                current_script,
                current_doc,
                self.harness_binary,
                self.harness_source,
                filetype_result,
                True,
                reference_script
            )
