SEEDGEN_SYSTEM_PROMPT = """
As a professional security engineer, your task is to develop a Python script that generates a new test case file. This file should adhere to the format required by the fuzzing harness code. The script will play a crucial role in creating diverse and effective test cases for thorough security testing.
"""

EXAMPLE_SCRIPT_PROMPT_1 = """
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

SEED_GENERATOR_FROM_SCRATCH_WITHOUT_FORMAT = """
Write a Python script that generates a test case file compatible with the required format of the fuzzing harness code. The generated test cases should be diverse and effective for security testing purposes. Consider various input types, edge cases, and potential vulnerabilities relevant to the system being tested. Ensure your script can produce a wide range of test scenarios to thoroughly exercise the target application or protocol.

## Requirements for the Python Script:
- Generate data that the provided fuzzing harness code can use (focus on structure and file format).
- Avoid importing unofficial third-party Python modules.

## Fuzzing Harness Code:
{harness_code}

## Available Tools:
- `view`: To view the source code of a function.
    - Usage: view(function_name: string) -> string
    - Returns: Source code of the function.
- `run`: To run the Python script to generate test case and get coverage information feedback.
    - Usage: run(full_python_code: string) -> string
    - Returns: Coverage information of the generated test cases.
    - The script is executed 50 times as `python3 /tmp/generator.py /tmp/generated_seedX`, where X is the seed number.

## Instructions and Steps:

0. (optional) Call the `view` tool to examine the source code of a function if hasn't been provided.

1. Call the `run` tool to submit your Python script.
    - Submit your Python script and check the returned coverage information.
    - You MUST include the full valid Python script when calling the run tool.

2. After submit, you will receive the coverage information as the tool-call returns. Write a short analysis of the current generator, including:
    - A 2-3 short sentences summary of the relationship between the script and the coverage. For example, "The script not cover part X because it generates only Y type of data."
    - A 2-3 short sentences general guideline on how to improve the script based on the coverage information received. You don't need to provide a new script, just some advice on how to improve the current one.

As an integrated component of an automated system, you should perform the tasks without seeking human confirmation or help.
Make sure to use the correct parameters when calling tools.
"""


COVERAGE_HISTORY = """
{coverage_hint}
"""

COVERAGE_HINT = """
Here is an example of the seed generation script for this harness code:
```python
{script}
```
Our coverage report indicates that the generated seeds with this script cover parts of the code:
{coverage}
(In the report, static functions and initializers are marked as uncovered. This is intentional, as these elements are not meant to be included in fuzzer coverage.)
To enhance code coverage, consider refining the script to produce more effective seeds. Here is some advice to help you improve the script:
{evaluation}
"""
