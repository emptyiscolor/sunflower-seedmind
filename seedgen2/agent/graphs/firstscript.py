# Initial Script Generator subgraph of SeedGen2

# Generating the initial version of a seed generation script, based purely on the source code of a fuzzing harness

import logging
from typing import List
from seedgen2.agent.cot import CoT
from seedgen2.agent.graphs.predicates import get_related_functions
from seedgen2.agent.presets import SeedGen2GenerativeModel, SeedGen2InferModel
from seedgen2.agent.sowbot import Sowbot
from seedgen2.utils.functions import FunctionInfo
from seedgen2.utils.grpc import SeedD
from seedgen2.utils.seeds import SeedFeedback

PROMTPT_GENERATE_FIRST_SCRIPT = """
You are a professional in the field of software security testing. Given the source code of a fuzzing harness, analyze the harness and generate a Python script that can be used to generate valid testcases for the given harness. Try your best to ensure the generated testcases cover as much harness code as possible. The generated test cases should be diverse and effective for security testing purposes. Consider various input types, edge cases, and potential vulnerabilities relevant to the system being tested. Ensure your script can produce a wide range of test scenarios to thoroughly exercise the target application or protocol.

Here is the source code of the harness:
{harness_source_code}
"""

def generate_first_script(
        seedd: SeedD,
        harness_source_code: str,
        harness_binary: str
):
    # Use generative model to generate the initial script
    model = SeedGen2GenerativeModel().model
    prompt = PROMTPT_GENERATE_FIRST_SCRIPT.format(
        harness_source_code=harness_source_code
    )

    sowbot = Sowbot(seedd, harness_binary, model=model)

    return sowbot.run(prompt)
