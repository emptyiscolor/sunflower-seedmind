import json
import subprocess
import os
import time
import uuid
import dotenv
dotenv.load_dotenv('myenv.env')
from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    SystemMessage,
    RemoveMessage,
)
from langchain_openai import ChatOpenAI

from langgraph.graph.message import add_messages
from langgraph.graph import START, END, StateGraph
from langchain_community.callbacks import get_openai_callback, OpenAICallbackHandler
from langchain_core.runnables import RunnableConfig

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
import shutil

# Define the GPT model
# model = ChatOpenAI(
#     model="gpt-4o-mini", api_key="sk-whexy", base_url="https://litellm.mudd.cc"
# )

# model = ChatOpenAI(
#     model="o1-mini",
#     api_key="sk-whexy",
#     base_url="https://litellm.mudd.cc",
# )

model = ChatOpenAI(
    model="gpt-4o"
)

# Define the state.
class State(TypedDict):
    # Predefined
    harness_binary: str
    shared_folder: str
    seeds_folder: str
    rt: runtime.SeedGenRuntime
    cb: OpenAICallbackHandler
    budget: float
    start_time: float
    max_level: int

    # States
    rounds: int
    messages: Annotated[list[AnyMessage], add_messages]
    harness_code: str
    generated_scripts: Annotated[list[str], add]
    generated_seeds: Annotated[list[str], add]
    coverage_reports: Annotated[list[str], add]
    suggestions: Annotated[list[str], add]

    # Flags
    over_token_limit: bool
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
    remove_commands = []
    for message in state["messages"]:
        remove_commands.append(RemoveMessage(id=message.id))

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

    # write prompt to prompt_{round}.txt in shared folder
    with open(
        os.path.join(state["shared_folder"], f"prompt_{state['rounds'] + 1}.txt"), "w"
    ) as f:
        f.write(prompt)
    
    # Some model doesn't support system message (e.g., o1-mini), so we add the system message prompt to the beginning of the user prompt
    prompt = SEEDGEN_SYSTEM_PROMPT + "\n\n" + prompt
    messages = [
        HumanMessage(content=prompt),
    ]

    try:
        response = model.invoke(messages)
    except Exception as e:
        if "maximum context length" in str(e).lower():
            new_max_level = (
                state["max_level"] - 1 if state["max_level"] is not None else 5
            )
            return {
                "max_level": new_max_level,
                "over_token_limit": True,
                "script_generated": False,
            }
        else:
            print(f"Error invoking model: {str(e)}")
            raise
    return {
        "rounds": state["rounds"] + 1,
        "messages": remove_commands + [response],
        "over_token_limit": False,
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
            + " Can you please fix the issue? Make sure your code run like this: `python3 generate.py <output_file_path>`"
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
    with open(f".tmp/generator_{state['rounds']}.py", "w") as f:
        f.write(generated_script)
    # Run the generated script
    seeds_folder = state["seeds_folder"]
    seeds_batch_id = str(uuid.uuid4())

    generated_seeds_files = []

    for i in range(50):
        try:
            result = subprocess.run(
                [
                    "python3",
                    f".tmp/generator_{state['rounds']}.py",
                    f"{seeds_folder}/{seeds_batch_id}_{i}",
                ],
                capture_output=True,
                text=True,
                timeout=30,  # Set the timeout to 30 seconds
            )
            if result.returncode != 0:
                print("[!] Failed to run the generated script.")
                return {
                    "seeds_generated": False,
                    "seeds_generation_failed_reason": f"stdout: {result.stdout}, stderr: {result.stderr}",
                }
            generated_seeds_files.append(f"{seeds_batch_id}_{i}")
        except subprocess.TimeoutExpired:
            print("[!] The script timed out.")
            return {
                "seeds_generated": False,
                "seeds_generation_failed_reason": "The script timed out after 30 seconds.",
            }

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

    # write coverage report to coverage_{round}.txt in shared folder
    with open(os.path.join(shared_folder, f"coverage_{state['rounds']}.txt"), "w") as f:
        f.write(coverage_report)

    coverage_info = coverage.parse_libfuzzer_log(coverage_report, levels)

    summary = []

    for func in coverage_info:
        if func["fully_covered"]:
            print(f"[+] Function {func['name']} is fully covered")
            continue

        if state["max_level"] is not None and func["level"] > state["max_level"]:
            continue

        filename, line = func["location"].split(":")

        shared_file = rt.share(filename)
        if shared_file is None:
            print(
                f"[-] Error: Failed to require the file from OSS-Fuzz docker container {filename} for function {func['name']}"
            )
            continue
        shared_filename = os.path.join(shared_folder, shared_file)
        source_code = source.get_function_source(shared_filename, func["name"])
        uncovered_lines = []
        for uncovered_pc in func["uncovered_pcs"]:
            uncovered_line_number = uncovered_pc.split(":")[1]
            uncovered_lines.append(int(uncovered_line_number))

        name = func["name"]
        coverages = f"Coverage (covered edges / total edges): {func['covered_edges']}/{func['total_edges']}"

        print(f"[+] Function {name} {coverages}")

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


def edge_over_token_limit(state: State):
    # if we successfully generate the seeds, and go over the token limit, we should turn back and retry with a smaller context level
    return state["over_token_limit"] and state["seeds_generated"]


def edge_should_stop(state: State):
    # return state["rounds"] >= 3
    # check if we're over budget

    total_cost = state["cb"].total_cost
    if total_cost == 0:
        # this model doesn't support cost tracking, but we still have token information
        input_price = 3 / 1_000_000  # $3 / 1M input tokens
        input_tokens = state["cb"].prompt_tokens

        output_price = 15 / 1_000_000  # $15 / 1M output tokens
        output_tokens = state["cb"].completion_tokens

        total_cost = input_tokens * input_price + output_tokens * output_price

    print("Current cost: ", total_cost)
    print("Budget: ", state["budget"])
    if total_cost >= state["budget"]:
        print("We're over budget, let's stop")
        return True
    else:
        # check if we've been running for more than 30 minutes
        if time.time() - state["start_time"] > 30 * 60:
            print("We've been running for more than 30 minutes, let's stop")
            return True
        else:
            print("Let's continue")
            return False


def start_seedgen(
    runtime_id: str,
    container_id: str,
    project_name: str,
    harness_binary: str,
    budget: float,
    max_level: int,
):
    # in order to connect to the SeedGen runtime service in the Docker container, we need to know the IP address of the container
    # we can use the container_id to get the IP address
    ip_addr = subprocess.run(
        [
            "docker",
            "inspect",
            "-f",
            "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
            container_id,
        ],
        capture_output=True,
        text=True,
    ).stdout.strip()

    print(
        f"[+] The SeedGen runtime service is running at {ip_addr}, waiting for it to be ready..."
    )

    runtime_folder = os.path.join(".tmp", runtime_id)
    shared_folder = os.path.join(runtime_folder, "shared")

    # Create a /seeds directory in the shared folder
    seeds_folder = os.path.join(shared_folder, "seeds")
    os.makedirs(seeds_folder, exist_ok=True)

    # Start SeedGen in the Docker container
    rt = runtime.SeedGenRuntime(ip_addr)
    rt.wait_until_ready()
    print(
        f"[+] SeedGen service is ready, starting the seed generation process for {project_name}/{harness_binary}"
    )

    # Locate the harness function
    harness_loc = rt.locate(f"/out/{harness_binary}", "LLVMFuzzerTestOneInput")
    if harness_loc is None:
        print("[-] Error: Harness function not found")
        return

    harness_filename = harness_loc[0]
    shared_file = rt.share(harness_filename)
    if shared_file is None:
        print(
            f"[-] Error: Failed to require the harness source code file {harness_filename} from OSS-Fuzz docker container"
        )
        return
    with open(os.path.join(shared_folder, shared_file), "r") as f:
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
    graph.add_conditional_edges(
        "agent_generation",
        edge_over_token_limit,
        {True: "system_evaluate_coverage", False: "system_fetch_code"},
    )
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
        "max_level": max_level,
        "rt": rt,
        "rounds": 0,
        "start_time": time.time(),
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

    os.makedirs(
        f"oss-fuzz/build/corpus/seedgen/{project_name}/{harness_binary}", exist_ok=True
    )

    with get_openai_callback() as cb:
        initial_state["cb"] = cb
        initial_state["budget"] = budget

        start_time = time.time()
        config = RunnableConfig(recursion_limit=1000)
        final_state = app.invoke(initial_state, config=config)
        end_time = time.time()
        total_duration = end_time - start_time

        profile = {
            "project_name": project_name,
            "harness_binary": harness_binary,
            "total_tokens": cb.total_tokens,
            "prompt_tokens": cb.prompt_tokens,
            "total_cost": cb.total_cost,
            "time": total_duration,
        }

        with open(
            f"oss-fuzz/build/corpus/seedgen/{project_name}/{harness_binary}.json",
            "w",
        ) as f:
            f.write(json.dumps(profile))

    for seed_file in final_state["generated_seeds"]:
        shutil.copy(
            f"{seeds_folder}/{seed_file}",
            f"oss-fuzz/build/corpus/seedgen/{project_name}/{harness_binary}/{seed_file}",
        )

    rt.close()
