from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from agent.workflow import SeedGen2GenerativeModel
from utils.generators import SeedGeneratorStore


class GenerateState(TypedDict):
    harness_code: str
    file_type: str
    feature: str
    # States
    messages: Annotated[list[AnyMessage], add_messages]
    generated_scripts: list[int]
    error_happened: bool
    error_message: str


PROMPT_generate = """
As a professional security engineer, your task is to develop a Python script that generates a new test case file. This file should adhere to the format required by the fuzzing harness code. The script will play a crucial role in creating diverse and effective test cases for thorough security testing.

Write a Python script that generates a {file_type} test case file with the feature of {feature}, compatible with the required format of the fuzzing harness code. The generated test cases should be diverse and effective for security testing purposes. Consider various input types, edge cases, and potential vulnerabilities relevant to the system being tested. Ensure your script can produce a wide range of test scenarios to thoroughly exercise the target application or protocol.

## Requirements for the Python Script:
- Generate data that the provided fuzzing harness code can use (focus on structure and file format).
- Avoid importing unofficial third-party Python modules.

## Fuzzing Harness Code:
{harness_code}

As an integrated component of an automated system, you should perform the tasks without seeking human confirmation or help.
Make sure to use the correct parameters when calling tools.

## Instructions and Steps:

- You MUST ensure the python code is wrapped in triple backticks for proper formatting, and it should be the only code your response.
- You MUST include the full valid Python script in your response.

## Requirements 

The script should:
1. Has one argument, which is the output file path.
2. Generate one test case and write it to the output file.
3. The generated test case should be compatible with the fuzzing harness code provided.

Here is an example of Python script used to generate a testcase file. You can use this as a reference to create your own script:

```python
#!/usr/bin/env python3

import sys
import random
import base64
from typing import BinaryIO

def generate_input(rng: BinaryIO, out: BinaryIO, original_data: bytes):
    # original_data: constants data for your reference
    # random_num = rng.read(1)[0] % 100 + 1
    # generated_data = ?
    out.write(generated_data)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 generate.py <output_file_path>")
        sys.exit(1)
    
    # replace it with constants that may be useful to the fuzzer
    original_data = b"0000"

    with open('/dev/urandom', 'rb') as rng, open(sys.argv[1], 'wb') as out:
        generate_input(rng, out, original_data)
```
"""


PROMPT_handle_generation_error = """
There is an error in the your generated script according to our automated testing. {error_message}

Please rewrite the script.
"""


def NODE_generate(state: GenerateState):
    model = SeedGen2GenerativeModel().model

    messages = [
        HumanMessage(content=PROMPT_generate.format(
            harness_code=state["harness_code"],
            file_type=state["file_type"],
            feature=state["feature"]))
    ]
    response = model.invoke(messages)
    messages.append(response)

    return {
        "messages": messages,
    }


def NODE_fetch_python_script(state: GenerateState):
    last_response = state["messages"][-1].content

    start = last_response.find("```python")
    end = last_response.find("```", start + 1)
    if start == -1 or end == -1:
        return {
            "error_happened": True,
            "error_message": "Unable to find the generated script. You should wrap your script in triple backticks like this: ```python\n...\n```",
        }

    generated_script = last_response[start + len("```python\n"): end].strip()
    store = SeedGeneratorStore()
    generator_id = store.new_generator(generated_script)

    print(f"[+] Generated script with ID: {generator_id}")

    # Let's try to run the generator
    run_result = store.run_generator(generator_id)
    if not run_result.is_success():
        print(f"[!] Failed to run generator: {run_result.get_error_message()}")
        return {
            "error_happened": True,
            "error_message": f"Failed to run generator: {run_result.get_error_message()}",
        }

    return {
        "error_happened": False,
        "generated_scripts": [generator_id],
    }


def NODE_handle_generation_error(state: GenerateState):
    model = SeedGen2GenerativeModel().model

    messages = [
        HumanMessage(content=PROMPT_handle_generation_error.format(
            error_message=state["error_message"]))
    ]
    response = model.invoke(state["messages"] + messages)
    messages.append(response)

    return {
        "messages": messages,
    }


def EDGE_error_happened(state: GenerateState) -> bool:
    return state["error_happened"]


def build_generate_graph():
    graph_builder = StateGraph(GenerateState)
    graph_builder.add_node("node_generate", NODE_generate)
    graph_builder.add_node("node_fetch_python_script",
                           NODE_fetch_python_script)
    graph_builder.add_node("node_handle_generation_error",
                           NODE_handle_generation_error)
    graph_builder.add_edge(START, "node_generate")
    graph_builder.add_edge("node_generate", "node_fetch_python_script")
    graph_builder.add_conditional_edges(
        "node_fetch_python_script",
        EDGE_error_happened,
        {
            True: "node_handle_generation_error",
            False: END,
        }
    )
    graph_builder.add_edge("node_handle_generation_error",
                           "node_fetch_python_script")
    return graph_builder.compile()


def GRAPH_generate(harness_code: str, file_type: str, feature: str):
    graph = build_generate_graph()

    initial_state = GenerateState(
        harness_code=harness_code,
        file_type=file_type,
        feature=feature,
        messages=[],
        generated_scripts=[],
        script_generated=False,
    )
    result = graph.invoke(initial_state, debug=True)

    return result
