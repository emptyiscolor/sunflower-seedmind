# Filetype subgraph of SeedGen2
# filetype stage is to generate the seeds with given harness source code, without any coverage information

# The agent will go through these steps:
# 1. given the harness source code, source code file name, project name, determine the filetype of the seeds.
# 2. if the filetype is determined, use the knowledgable model to write description for the filetype, and features for the filetype.
# 3. for each feature, use the generative model to write a seed generator.
# 4. if the filetype is not determined, use the generative model to write a seed generator directly.

from dataclasses import dataclass
from seedgen2.agent.seedson import seedson
from seedgen2.agent.sowbot import Sowbot, SowbotResult
from seedgen2.utils.grpc import SeedD


@dataclass
class FileTypeInfo:
    file_type: str
    features: list[str]


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

PROMPT_generate = """
As a professional security engineer, your task is to develop a Python script that generates a new test case file. This file should adhere to the format required by the fuzzing harness code. The script will play a crucial role in creating diverse and effective test cases for thorough security testing.

Write a Python script that generates a {file_type} test case file with the feature of {feature}, compatible with the required format of the fuzzing harness code. The generated test cases should be diverse and effective for security testing purposes. Consider various input types, edge cases, and potential vulnerabilities relevant to the system being tested. Ensure your script can produce a wide range of test scenarios to thoroughly exercise the target application or protocol.


## Fuzzing Harness Code:
{harness_code}
"""


def get_filetype(harness_source_code: str, harness_file_name: str, project_name: str) -> FileTypeInfo:
    # Build the prompt
    prompt = PROMPT_determine_file_type.format(
        harness_source_code=harness_source_code,
        harness_file_name=harness_file_name,
        project_name=project_name
    )

    # Define the JSON schema
    json_schema = {
        "type": "object",
        "properties": {
            "file_type": {"type": "string"},
            "features": {
                "type": "array",
                "items": {"type": "string"}
            }
        },
        "required": ["file_type", "features"]
    }

    # Build the graph
    result = seedson(prompt, json_schema)

    return FileTypeInfo(
        file_type=result['file_type'],
        features=result['features'],
    )


def generate_based_on_filetype(seedd: SeedD, harness_binary: str, harness_source_code: str, filetype_info: FileTypeInfo) -> SowbotResult:
    sowbot = Sowbot(seedd, harness_binary)
    # TODO: generate multiple seed groups for each feature
    prompt = PROMPT_generate.format(
        harness_code=harness_source_code,
        file_type=filetype_info.file_type,
        feature=filetype_info.features[0],
    )
    return sowbot.run(prompt)
