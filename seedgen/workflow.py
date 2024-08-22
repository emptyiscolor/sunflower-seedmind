import subprocess
import os
import uuid

from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    SystemMessage,
    RemoveMessage,
)
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.pydantic_v1 import BaseModel

from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, END, StateGraph, MessagesState
from langgraph.prebuilt import ToolNode

from typing import Annotated, TypedDict

from operator import add

from .prompt_template import (
    SEED_GENERATOR_FROM_SCRATCH,
    EXAMPLE_SCRIPT_PROMPT_1,
    EXAMPLE_SCRIPT_PROMPT_2,
    SEEDGEN_SYSTEM_PROMPT,
    SUMMARY_PROMPT,
)

from . import runtime, callgraph, coverage, source

# Define the GPT model
model = ChatOpenAI(
    model="gpt-4o-mini", api_key="sk-whexy", base_url="https://litellm.mudd.cc"
)


# Define the state.
class State(TypedDict):
    # Predefined
    harness_binary: str
    shared_folder: str
    seeds_folder: str
    rt: runtime.SeedGenRuntime

    # States
    rounds: int
    messages: Annotated[list[AnyMessage], add_messages]
    harness_code: str
    generated_scripts: Annotated[list[str], add]
    generated_seeds: Annotated[list[str], add]
    coverage_reports: Annotated[list[str], add]
    suggestions: Annotated[list[str], add]
    script_generated: bool
    seeds_generated: bool
    seeds_generation_failed_reason: str
    coverage_generated: bool
    suggestions_generated: bool


# Define the nodes
# We use a naming convention to make it easier to understand the code.
#   1. All nodes should start with "node_"
#   2. If the node is a tool, it should be named "node_tool_".
#      If the node is an agent, it should be named "node_agent_".


# Based on the state, generate a prompt for the model and get the response.
def node_agent_generation(state: State):
    print("[+] Start agent generation, round ", state["rounds"] + 1)
    prompt = SEED_GENERATOR_FROM_SCRATCH.format(harness_code=state["harness_code"])
    if state["rounds"] == 0:
        # Fresh start
        prompt += "\n\n" + EXAMPLE_SCRIPT_PROMPT_1
    else:
        # Improve the script based on the feedback
        prompt += "\n\n" + EXAMPLE_SCRIPT_PROMPT_2.format(
            script=state["generated_scripts"][-1],
            coverage=state["coverage_reports"][-1],
            suggestions=state["suggestions"][-1],
        )
    messages = state["messages"]
    messages.append(HumanMessage(content=prompt))
    response = model.invoke(messages)
    return {
        "rounds": state["rounds"] + 1,
        "messages": [response],
    }


# Our system failed to fetch the response code from the model, or code cannot be executed.
def node_agent_generation_retry(state: State):
    retry_prompt = ""

    if not state["script_generated"]:
        # failed to extract the Python code from the response
        retry_prompt = "Failed to extract the Python code from your response. Can you please try again? Make sure to include the Python code in triple backticks, and it should be the only code in your response."
    elif state["script_generated"] and not state["seeds_generated"]:
        retry_prompt = (
            "Failed to generate the seeds from the Python code. The error message is: "
            + state["seeds_generation_failed_reason"]
            + " Can you please fix the issue?"
        )
    else:
        pass

    messages = state["messages"]
    messages.append(HumanMessage(content=retry_prompt))
    response = model.invoke(messages)

    return {
        "messages": [response],
    }


# Fetch the response code from the model.
def node_system_fetch_code(state: State):
    last_response = state["messages"][-1].content
    start = last_response.find("```python")
    end = last_response.find("```", start + 1)
    if start == -1 or end == -1:
        return {
            "script_generated": False,
        }
    else:
        generated_script = last_response[start + len("```python\n") : end].strip()
        return {
            "generated_scripts": [generated_script],
            "script_generated": True,
        }


# Run the generated script to generate the seeds.
def node_system_run_generated_script(state: State):
    generated_script = state["generated_scripts"][-1]
    with open("/tmp/generator.py", "w") as f:
        f.write(generated_script)
    # Run the generated script
    seeds_folder = state["seeds_folder"]
    seeds_batch_id = str(uuid.uuid4())

    generated_seeds_files = []

    for i in range(50):
        result = subprocess.run(
            ["python3", "/tmp/generator.py", f"{seeds_folder}/{seeds_batch_id}_{i}"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print("[!] Failed to run the generated script.")
            return {
                "seeds_generated": False,
                "seeds_generation_failed_reason": result.stderr,
            }
        generated_seeds_files.append(f"{seeds_batch_id}_{i}")

    print(f"[+] Seeds generated successfully in {seeds_folder}")
    return {
        "seeds_generated": True,
        "generated_seeds": generated_seeds_files,
    }


# Evaluate the coverage of the generated seeds.
def node_system_evaluate_coverage(state: State):
    rt = state["rt"]
    rt.wait_until_ready()

    harness_binary = state["harness_binary"]
    shared_folder = state["shared_folder"]
    generated_seeds = state["generated_seeds"]

    calls_report = rt.export_calls(
        f"/out/{harness_binary}", [f"/shared/seeds/{i}" for i in generated_seeds]
    )  # this is a filename in the shared folder
    if calls_report is None:
        print("[-] Error: Failed to export calls")
        return

    report_file = os.path.join(shared_folder, calls_report)
    levels = callgraph.process_call_graph(report_file)

    coverage_report = rt.run(
        f"/out/{harness_binary}", [f"/shared/seeds/{i}" for i in generated_seeds]
    )
    coverage_info = coverage.parse_libfuzzer_log(coverage_report, levels)

    summary = []

    for func in coverage_info:
        if func["fully_covered"]:
            continue

        filename, line = func["location"].split(":")

        shared_filename = os.path.join(shared_folder, rt.share(filename))
        source_code = source.get_function_source(shared_filename, func["name"])
        uncovered_lines = []
        for uncovered_pc in func["uncovered_pcs"]:
            uncovered_line_number = uncovered_pc.split(":")[1]
            uncovered_lines.append(int(uncovered_line_number))

        name = func["name"]
        coverages = f"Coverage (covered edges / total edges): {func['covered_edges']}/{func['total_edges']}"

        prompt = f"Function Information:\n" f"Name: {name}\n" f"{coverages}\n"

        summary.append(prompt)

        if source_code is None:
            # in this case, we can guess the function source from the coverage info
            first_known_line = int(line) - 1
            last_known_line = max(uncovered_lines + [first_known_line])
            summary.append(
                f"source code (maybe incomplete) from line {first_known_line} to {last_known_line}:"
            )
            with open(shared_filename, "r") as f:
                lines = f.readlines()
                function_source = lines[first_known_line : last_known_line + 10]
                for i, line_content in enumerate(
                    function_source, start=first_known_line + 1
                ):
                    if i in uncovered_lines:
                        summary.append(f"[MISSING]\t{line_content.rstrip()}")
                    else:
                        summary.append(f"[       ]\t{line_content.rstrip()}")
            continue

        for line, content in source_code:
            if line in uncovered_lines:
                summary.append(f"[MISSING]\t{content}")
            else:
                summary.append(f"[       ]\t{content}")

    return {
        "coverage_reports": ["\n".join(summary)],
    }


def node_agent_suggestions(state: State):
    coverage_report = state["coverage_reports"][-1]

    messages = state["messages"]
    messages.append(
        HumanMessage(content=SUMMARY_PROMPT.format(coverage_report=coverage_report))
    )
    response = model.invoke(messages)

    return {
        "messages": [response],
        "suggestions": [response.content],
    }


# Define the conditional edges
def edge_script_generated(state: State):
    return state["script_generated"]


def edge_seeds_generated(state: State):
    return state["seeds_generated"]


def edge_should_stop(state: State):
    return state["rounds"] >= 3


def start_seedgen(runtime_id: str, harness_binary: str):
    runtime_folder = os.path.join("/tmp", runtime_id)
    shared_folder = os.path.join(runtime_folder, "shared")

    # Create a /seeds directory in the shared folder
    seeds_folder = os.path.join(shared_folder, "seeds")
    os.makedirs(seeds_folder, exist_ok=True)

    # Start SeedGen in the Docker container
    rt = runtime.SeedGenRuntime()
    rt.wait_until_ready()
    print("[+] SeedGen service is ready, starting the seed generation process...")

    # Locate the harness function
    harness_loc = rt.locate(f"/out/{harness_binary}", "LLVMFuzzerTestOneInput")
    if harness_loc is None:
        print("[-] Error: Harness function not found")
        return

    harness_filename = harness_loc[0]
    with open(os.path.join(shared_folder, rt.share(harness_filename)), "r") as f:
        harness_code = f.read()
    print(f"[+] Harness function found at {harness_filename}")

    graph = StateGraph(State)
    graph.add_node("agent_generation", node_agent_generation)
    graph.add_node("agent_generation_retry", node_agent_generation_retry)
    graph.add_node("agent_suggestions", node_agent_suggestions)
    graph.add_node("system_fetch_code", node_system_fetch_code)
    graph.add_node("system_run_generated_script", node_system_run_generated_script)
    graph.add_node("system_evaluate_coverage", node_system_evaluate_coverage)

    graph.add_edge(START, "agent_generation")
    graph.add_edge("agent_generation", "system_fetch_code")
    graph.add_conditional_edges(
        "system_fetch_code",
        edge_script_generated,
        {True: "system_run_generated_script", False: "agent_generation_retry"},
    )
    graph.add_edge("agent_generation_retry", "system_fetch_code")
    graph.add_conditional_edges(
        "system_run_generated_script",
        edge_seeds_generated,
        {True: "system_evaluate_coverage", False: "agent_generation_retry"},
    )
    graph.add_edge("system_evaluate_coverage", "agent_suggestions")
    graph.add_conditional_edges(
        "agent_suggestions", edge_should_stop, {True: END, False: "agent_generation"}
    )

    app = graph.compile()
    print(app.get_graph().draw_mermaid())

    initial_state = {
        "harness_binary": harness_binary,
        "shared_folder": shared_folder,
        "seeds_folder": seeds_folder,
        "rt": rt,
        "rounds": 0,
        "messages": [
            SystemMessage(content=SEEDGEN_SYSTEM_PROMPT),
        ],
        "harness_code": harness_code,
        "generated_scripts": [],
        "generated_seeds": [],
        "coverage_reports": [],
        "suggestions": [],
        "script_generated": False,
        "seeds_generated": False,
        "coverage_generated": False,
        "suggestions_generated": False,
    }

    final_state = app.invoke(initial_state)
    print(final_state["messages"][-1].content)

    rt.close()
