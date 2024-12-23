# Structure Documentation Generator subgraph of SeedGen2

# 1. Given the harness and its related functions, generate a plaintext documentation describing the required structure of a testcase
# 2. In the subsequent rounds, given the previous documentation and additional harness information, improve the structure documentation

import os
import logging
from typing import List
from seedgen2.agent.graphs.predicates import get_related_functions
from seedgen2.agent.presets import SeedGen2InferModel
from seedgen2.agent.sowbot import Sowbot
from seedgen2.utils.functions import FunctionInfo
from seedgen2.utils.grpc import SeedD
from seedgen2.utils.seeds import SeedFeedback

PROMPT_GENERATE_STRUCTURE_DOCUMENTATION = """
Given the source code of a fuzzing harness, please analyze it and write down the required structure of the test cases.

Here is the source code of the all related functions in the harness:
{related_functions}

As a result, you should write detailed structure documentation of the harness, consisting of a comprehensive and easily digestable plaintext description, including but not limited to:

- Headers or metadata fields and their characteristics.
- Specific data fields: location, type, encoding method, etc.
- Emphasize usage of common file types' contents within the test structure: their location, fields, specific requirements, etc.
- Other specific requirements.

Please ONLY give the detailed test case structure, and DO NOT include any concrete examples or guidance.
"""

PROMPT_IMPROVE_STRUCTURE_DOCUMENTATION = """
I am working on writing a documentation about the structure of a test case for a specific test harness. However, I've noticed that the current version of my documentation doesn't fully document everything that a test case requires. Therefore, I need your help to improve my test case structure documentation. Your tasks are:

- Analyze the source code of the harness and fully understand it.
- Find out the parts in the harness source that are not documented in the documentation, and add them to the documentation.
- Find out if there are any parts in the documentation that are incorrect, i.e. don't align with the source code, and correct them.

Here is the source code of the all related functions in the harness:
{related_functions}

Here is the current test case structure documentation:
{structure_documentation}

Please ONLY include the updated test case structure documentation in your response, and DO NOT include any concrete examples or guidance.
"""

def generate_first_documentation(
        seedd: SeedD,
        seed_feedback: SeedFeedback,
        functions: List[FunctionInfo],
        log_dir: str
):
    entrance_function = next(
        (func for func in seed_feedback.partially_covered_functions if func.function_name ==
         "LLVMFuzzerTestOneInput"),
        None
    )

    if entrance_function is None:
        logging.info("Entrance function is not found or is fully covered.")
        return

    related_functions = get_related_functions(
        seedd, functions, entrance_function.function_name)

    # Use infer model to generate the format analysis
    infer_model = SeedGen2InferModel().model
    prompt = PROMPT_GENERATE_STRUCTURE_DOCUMENTATION.format(
        related_functions=related_functions
    )

    prompt_file_path = os.path.join(log_dir, f"prompt_doc_0.txt")
    
    with open(prompt_file_path, "w") as f:
        f.write(prompt)

    return infer_model.invoke(prompt).content # TODO: error handling

def improve_documentation(
        seedd: SeedD,
        seed_feedback: SeedFeedback,
        functions: List[FunctionInfo],
        structure_documentation: str,
        log_dir: str,
        round_cnt: int
):
    entrance_function = next(
        (func for func in seed_feedback.partially_covered_functions if func.function_name ==
         "LLVMFuzzerTestOneInput"),
        None
    )

    if entrance_function is None:
        logging.info("Entrance function is not found or is fully covered.")
        return

    related_functions = get_related_functions(
        seedd, functions, entrance_function.function_name)

    # Use infer model to generate the format analysis
    infer_model = SeedGen2InferModel().model
    prompt = PROMPT_IMPROVE_STRUCTURE_DOCUMENTATION.format(
        related_functions=related_functions,
        structure_documentation=structure_documentation
    )

    prompt_file_path = os.path.join(log_dir, f"prompt_doc_{round_cnt}.txt")
    
    with open(prompt_file_path, "w") as f:
        f.write(prompt)

    return infer_model.invoke(prompt).content # TODO: error handling

