import os
import time
import logging
from dotenv import load_dotenv
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents.output_parsers.openai_tools import OpenAIToolsAgentOutputParser
from langchain.agents import AgentExecutor
from langchain.agents.format_scratchpad.openai_tools import (
    format_to_openai_tool_messages,
)

from service import SeedGenService

from .tools import create_viewfunction_tool, create_run_generator_tool
from .prompt_template import (
    SEEDGEN_SYSTEM_PROMPT,
    SEED_GENERATOR_FROM_SCRATCH_WITHOUT_FORMAT,
    EXAMPLE_SCRIPT_PROMPT_1,
    COVERAGE_HINT,
    COVERAGE_HISTORY,
)
from .coverage import CoverageCenter

from config import SEEDGEN_PATH

logger = logging.getLogger(__name__)


class OpenAIAgent:
    def __init__(
        self,
        harness: str,  # binary name of the harness (not id)
        service: SeedGenService,
        coverage_center: CoverageCenter,
        script_id: int,
        model: str = "gpt-4o",
        temperature: float = 1,
        max_iterations: int = 10,
    ):
        load_dotenv()
        OPENAI_BASE_URL = os.environ.get("AIXCC_LITELLM_HOSTNAME")
        OPENAI_API_KEY = os.environ.get("LITELLM_KEY")

        logger.info(f"Using OpenAI API Key: {OPENAI_API_KEY}")
        logger.info(f"Using OpenAI Base URL: {OPENAI_BASE_URL}")

        self.script_id = script_id
        self.coverage_center = coverage_center
        self.model = model
        self.temperature = temperature
        self.max_iterations = max_iterations
        self.llm = ChatOpenAI(
            temperature=temperature,
            model=model,
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL,
        )

        self.langchain_tools = [
            create_viewfunction_tool(harness, service),
            create_run_generator_tool(harness, service, coverage_center, script_id),
            # add more tools here
        ]
        self.openai_tools = [
            convert_to_openai_tool(tool) for tool in self.langchain_tools
        ]

        self.llm = self.llm.bind_tools(self.openai_tools)

    def generate_generator(self, harness_code) -> AgentExecutor:
        coverage_hint_message = ""
        if self.script_id > 0:
            # This is not the first script, so we can get coverage hints.
            for script_id in range(self.script_id):
                script_info = self.coverage_center.get_info(script_id)
                if script_info is None:
                    continue
                script = script_info["script"]
                coverage = script_info["coverage"]
                evaluation = script_info["evaluation"]
                coverage_hint_message += COVERAGE_HINT.format(
                    script_id=script_id,
                    script=script,
                    coverage=coverage,
                    evaluation=evaluation,
                )

        prompt_template = ChatPromptTemplate.from_messages(
            [
                ("system", SEEDGEN_SYSTEM_PROMPT),
                ("user", EXAMPLE_SCRIPT_PROMPT_1),
                ("user", SEED_GENERATOR_FROM_SCRATCH_WITHOUT_FORMAT),
                ("user", COVERAGE_HISTORY),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ]
        )

        prompt = {
            "coverage_hint": lambda input: coverage_hint_message,
            "harness_code": lambda input: harness_code,
            "agent_scratchpad": lambda input: format_to_openai_tool_messages(
                input["intermediate_steps"]
            ),
        } | prompt_template

        agent = prompt | self.llm | OpenAIToolsAgentOutputParser()

        executor = AgentExecutor(
            agent=agent,
            tools=self.langchain_tools,
            verbose=True,
            max_iterations=self.max_iterations,
        )

        output = executor.invoke({})

        if self.script_id not in self.coverage_center.coverage_data:
            # this means that no script generated, but the chain finished.
            # Restart the chain
            self.generate_generator(harness_code)
        else:
            self.coverage_center.store_evaluation(self.script_id, output["output"])


def start_seedgen(
    service: SeedGenService, cp: str, harness_binary: str
) -> None:

    # If LOOP_ROUNDS is set
    if os.getenv("LOOP_ROUNDS"):
        loop_rounds = int(os.getenv("LOOP_ROUNDS"))
        logger.info(f"Looping for {loop_rounds} rounds.")
    else:
        loop_rounds = 5

    shared_folder = f"{SEEDGEN_PATH}/{cp}/output/{harness_binary}"
    container_folder = f"/seedgen_output/{harness_binary}"
    coverage_center = CoverageCenter(shared_folder, container_folder)

    try:
        logger.info(
            f"Calling locate with binary: {harness_binary}"
        )
        response = service.locate(harness_binary, "LLVMFuzzerTestOneInput")
        if not response:
            logger.error("Failed to locate LLVMFuzzerTestOneInput function.")
            return

        filename, line = response
        logger.info(f"Received harness source: {filename}:{line}")

        # View harness source code
        logger.info(
            f"Calling view with filename: {filename}, line: {line}"
        )
        source_code = service.view(filename, line)
        if not source_code:
            logger.error("Failed to view harness source code.")
            return

        for script_id in range(loop_rounds):
            try:
                agent = OpenAIAgent(
                    harness_binary,
                    service,
                    coverage_center,
                    script_id,
                    model="oai-gpt-4o",
                )
                agent.generate_generator(source_code)
            except Exception as e:
                logger.error(f"Failed to generate seeds: {e}")
                continue
    finally:
        service.close()
