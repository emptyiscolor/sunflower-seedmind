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
Help me determine if there is a common file type that is being used as part of a test case for this fuzzing harness. In other words, based on the source code of the harness, you need to determine any potential common file type that is being used.

The project under test's name is {project_name}.
Here is the source code of the harness `{harness_file_name}`:
```
{harness_source_code}
```

You should return the file type that you recognize in a JSON format, with the following fields:
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
I am working on a fuzzing project and have developed a Python script to generate test cases for a fuzzing harness. However, I noticed that the test harness might make use of a specific common file type called {file_type}, containing the feature of {feature}, which is not fully utilized in the current generation script. Therefore, I need your help to improve the script to encompass the generation of this file type's content as part of the test case generation, in order to increase the overall test coverage.

Here is the current python script:
{script}

After the improvement, with the addition of generating {file_type} content, the format of the generated test cases from this script should still follow the format required by the fuzzing harness code, as described in the following documentation:
{format_analysis}
"""


def get_filetype(
        harness_source_code: str, 
        harness_file_name: str, 
        project_name: str
) -> FileTypeInfo:
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

    # TODO: error handling for when seedson's result doesn't have file_type and/or features fields
    return FileTypeInfo(
        file_type=result['file_type'],
        features=result['features'],
    )


def generate_based_on_filetype(
        seedd: SeedD, 
        script: str,
        format_analysis: str,
        harness_binary: str, 
        harness_source_code: str, 
        filetype_info: FileTypeInfo
) -> SowbotResult:
    sowbot = Sowbot(seedd, harness_binary, include_example=False)
    # TODO: generate multiple seed groups for each feature
    # TODO: handle unknown file type
    prompt = PROMPT_generate.format(
        harness_code=harness_source_code,
        file_type=filetype_info.file_type,
        feature=filetype_info.features[0],
        script=script,
        format_analysis=format_analysis
    )
    return sowbot.run(prompt)
