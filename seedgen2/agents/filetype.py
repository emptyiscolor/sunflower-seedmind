# Filetype subgraph of SeedGen2
# filetype stage is to improve the seed generation script, using information about common file types

from seedgen2.graphs.plainbot import Plainbot
from seedgen2.graphs.sowbot import Sowbot, SowbotResult
from seedgen2.utils.grpc import SeedD

from seedgen2.presets import SeedGen2KnowledgeableModel

PROMPT_determine_file_type = """
Help me determine if there is a common file type that is being used as part of a test case for this fuzzing harness. In other words, based on the source code of the harness, you need to determine any potential common file type that is being used.

The project under test's name is {project_name}.
Here is the source code of the harness `{harness_file_name}`:
```
{harness_source_code}
```

You should return only the name of the file type in your response, and nothing else, e.g. `jpg`, `png`, `gif`, etc. If the file type is not determined (or not a common known file type), you should return `unknown`.
"""

PROMPT_generate = """
I am working on a fuzzing project and have developed a Python script to generate test cases for a fuzzing harness. However, I noticed that the test harness might make use of a specific common file type called {file_type}. Currently, the test case generation script only generates a small limited amount of {file_type} file content, in a hard-coded manner. Therefore, I need your help to improve the script to encompass a more diverse and structural generation of this file type's content as part of the test case generation, in order to increase the overall test coverage.

Here is the current python script:
{script}

After the improvement, with the addition of generating {file_type} content, the overall structure of the generated test cases from this script should still follow the structure required by the fuzzing harness code, as described in the following documentation:
{structure_documentation}
"""


def get_filetype(
        harness_source_code: str,
        harness_file_name: str,
        project_name: str
) -> str:
    # Build the prompt
    prompt = PROMPT_determine_file_type.format(
        harness_source_code=harness_source_code,
        harness_file_name=harness_file_name,
        project_name=project_name
    )

    knowledgeable_model = SeedGen2KnowledgeableModel().model

    plainbot = Plainbot(model=knowledgeable_model)
    return plainbot.run(prompt)


def generate_based_on_filetype(
        seedd: SeedD,
        script: str,
        structure_documentation: str,
        harness_binary: str,
        harness_source_code: str,
        filetype_info: str
) -> SowbotResult:
    sowbot = Sowbot(seedd, harness_binary, include_example=False)
    # TODO: handle unknown file type
    prompt = PROMPT_generate.format(
        harness_code=harness_source_code,
        file_type=filetype_info,
        script=script,
        structure_documentation=structure_documentation
    )
    return sowbot.run(prompt)
