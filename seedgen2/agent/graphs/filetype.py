# Initial subgraph of SeedGen2
# Initial stage is to generate the seeds with given harness source code, without any coverage information

# The agent will go through these steps:
# 1. given the harness source code, source code file name, project name, determine the filetype of the seeds.
# 2. if the filetype is determined, use the knowledgable model to write description for the filetype, and features for the filetype.
# 3. for each feature, use the generative model to write a seed generator.
# 4. if the filetype is not determined, use the generative model to write a seed generator directly.

from dataclasses import dataclass
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AnyMessage
from seedgen2.agent.presets import SeedGen2KnowledgeableModel
from seedgen2.agent.sowbot import Sowbot
import json
import logging

from seedgen2.utils.grpc import SeedD


@dataclass
class FileTypeInfo:
    file_type: str
    features: list[str]


class InitialState(TypedDict):
    harness_source_code: str
    harness_file_name: str
    project_name: str

    # states
    file_type_determined: bool
    file_type: str
    file_type_features: list[str]

    # error message
    error_happened: bool
    error_message: str

    # chat history
    messages: Annotated[list[AnyMessage], add_messages]


# TODO: write a better prompt for the knowledgeable model
PROMPT_determine_file_type = """
Help me determine the file type of fuzzing seeds.
For a given project, we already have a test harness for fuzzing testing purpose. Based on the source code of the harness, you need to determine the file type of the seeds.

Here is the project {project_name}:
Here is the source code of the harness `{harness_file_name}`:
```
{harness_source_code}
```

You should return the file type of the seeds in a JSON format, with the following fields:
- file_type: the file type of the seeds, e.g. `jpg`, `png`, `gif`, etc. If the file type is not determined (or not a common known file type), you should return `unknown`.
- features: a list of interesting features of the file type, e.g. "Color Space", "Chroma Subsampling", "Progressive Encoding", etc.

Here is an example of the JSON format:
```json
{{
    "file_type": "jpg",
    "features": ["Color Space", "Chroma Subsampling", "Progressive Encoding"]
}}
```
"""

PROMPT_rewrite_json_if_needed = """
There is an error in the JSON object you returned. Please rewrite the JSON object.

Here is the error message:
{error_message}

Here is an example of the JSON format:
```json
{{
    "file_type": "jpg",
    "features": ["Color Space", "Chroma Subsampling", "Progressive Encoding"]
}}
```
"""

PROMPT_generate = """
As a professional security engineer, your task is to develop a Python script that generates a new test case file. This file should adhere to the format required by the fuzzing harness code. The script will play a crucial role in creating diverse and effective test cases for thorough security testing.

Write a Python script that generates a {file_type} test case file with the feature of {feature}, compatible with the required format of the fuzzing harness code. The generated test cases should be diverse and effective for security testing purposes. Consider various input types, edge cases, and potential vulnerabilities relevant to the system being tested. Ensure your script can produce a wide range of test scenarios to thoroughly exercise the target application or protocol.


## Fuzzing Harness Code:
{harness_code}

"""


def NODE_determine_file_type(state: InitialState):
    knowledgeable_model = SeedGen2KnowledgeableModel().json_model
    messages = [
        HumanMessage(content=PROMPT_determine_file_type.format(
            harness_source_code=state["harness_source_code"],
            harness_file_name=state["harness_file_name"],
            project_name=state["project_name"]
        ))
    ]

    response = knowledgeable_model.invoke(messages)
    messages.append(response)

    return {
        "messages": messages,
    }


def NODE_grab_json_from_response(state: InitialState):
    response = state["messages"][-1].content
    try:
        json_obj = json.loads(response)
        logging.info(f"[*] File type determined: {json_obj['file_type']}")
        logging.info(f"[*] File type features: {json_obj['features']}")
        return {
            "file_type_determined": True,
            "file_type": json_obj["file_type"],
            "file_type_features": json_obj["features"],
        }
    except Exception as e:
        logging.error(f"[!] Failed to parse JSON from response: {
                      e}, response: {response}")
        return {
            "file_type_determined": False,
            "error_happened": True,
            "error_message": f"Failed to parse JSON from response: {e}",
        }


def NODE_rewrite_json_if_needed(state: InitialState):
    knowledgeable_model = SeedGen2KnowledgeableModel().json_model
    messages = [
        HumanMessage(content=PROMPT_rewrite_json_if_needed.format(
            error_message=state["error_message"],
        ))
    ]
    messages.append(knowledgeable_model.invoke(state["messages"] + messages))
    return {
        "messages": messages,
    }


def EDGE_error_happened(state: InitialState) -> bool:
    return state["error_happened"]


def build_initial_graph():
    graph_builder = StateGraph(InitialState)
    graph_builder.add_node("node_determine_file_type",
                           NODE_determine_file_type)
    graph_builder.add_node("node_grab_json_from_response",
                           NODE_grab_json_from_response)
    graph_builder.add_node("node_rewrite_json_if_needed",
                           NODE_rewrite_json_if_needed)

    graph_builder.add_edge(START, "node_determine_file_type")
    graph_builder.add_edge("node_determine_file_type",
                           "node_grab_json_from_response")
    graph_builder.add_conditional_edges(
        "node_grab_json_from_response",
        EDGE_error_happened,
        {
            True: "node_rewrite_json_if_needed",
            False: END,
        }
    )
    graph_builder.add_edge("node_rewrite_json_if_needed",
                           "node_grab_json_from_response")

    return graph_builder.compile()


def get_filetype(harness_source_code: str, harness_file_name: str, project_name: str) -> FileTypeInfo:
    graph = build_initial_graph()

    initial_state = InitialState(
        harness_source_code=harness_source_code,
        harness_file_name=harness_file_name,
        project_name=project_name,
        file_type_determined=False,
        file_type="",
        file_type_features=[],
        messages=[],
        error_happened=False,
        error_message="",
    )

    result = graph.invoke(initial_state)

    return FileTypeInfo(
        file_type=result["file_type"],
        features=result["file_type_features"],
    )


def generate_based_on_filetype(seedd: SeedD, harness_binary: str, harness_source_code: str, filetype_info: FileTypeInfo):
    sowbot = Sowbot(seedd, harness_binary)
    prompt = PROMPT_generate.format(
        harness_code=harness_source_code,
        file_type=filetype_info.file_type,
        feature=filetype_info.features[0],
    )
    return sowbot.run(prompt)
