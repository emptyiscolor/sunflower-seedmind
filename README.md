# SeedGen2 (Project Sunflower)

## Overview

SeedGen2 is a framework designed to generate initial seeds for OSS-Fuzz, enhancing the effectiveness of fuzzing. By leveraging the capabilities of large language models, SeedGen2 can create valid seeds and improve them using harness and coverage information.

## Agent

SeedGen2 utilizes a variety of agents to generate seeds by analyzing both static and dynamic project information. This includes:

- Project harnesses code
- Dictionaries (string literals within the program)
- Documentation
- Source code
- Dynamic code coverage
- Call relationships
- Predicates

These elements collectively aid in the seed generation process.

SeedGen2 is built to be flexible and extensible, enabling the integration of additional agents to further enhance its functionality.

## Architecture

SeedGen2 consists of two main components:
1. **Lightweight Runtime `SeedD`**: Runs the fuzzing harness within an OSS-Fuzz Docker container, collecting dynamic information.
2. **LLM Agents**: Capable of self-reflection and guided by a state machine to ensure tasks are managed effectively and LLM errors are preemptively fixed.

## Getting Started

### Prerequisites
- Docker
- Python 3.x

## Usage

1. **Build the Tool**
   ```shell
   make
   ```

2. **Run the Script**
   ```shell
   python3 oss-fuzz.py <project_name> <harness_name>
   ```
   - **Project Name**: Directory name in `oss-fuzz/projects/`, e.g., `libxml2`.
   - **Harness Name**: Executable file in the `/out` folder after building the project.

### Example
To run SeedGen2 for the `libxml2` project with the `xml` harness:
```shell
python3 oss-fuzz.py libxml2 xml
```

To run seedmind for libxml2 project for all harnesses:

```shell
# set up the LiteLLM variables
export LITELLM_BASE_URL=https://your.litellm.host
export LITELLM_KEY=sk-your_private_key
export SEEDGEN_KNOWLEDGEABLE_MODEL=openai/gpt-5-mini
export SEEDGEN_GENERATIVE_MODEL=openai/gpt-5-mini
export SEEDGEN_INFER_MODEL=openai/gpt-5.1
export GEN_MODEL_LIST=openai/gpt-5-mini,openai/gpt-5.1
export OSSFUZZ_PATH=/workspaces/oss-fuzz-harnessagent

# src_path is the external source code path of target project

python infra/oss-fuzz.py --root /workspaces/oss-fuzz-harnessagent --model gpt-5-mini --src_path "$src_path" libxml2 --all
```

### Run with Docker:

set up the environment variables

```shell
cat <<'EOF' > .env
PYTHONPATH=/app
LITELLM_BASE_URL=https://your.litellm.host
LITELLM_KEY=sk-your_private_key
SEEDGEN_KNOWLEDGEABLE_MODEL=openai/gpt-5-mini
SEEDGEN_GENERATIVE_MODEL=openai/gpt-5-mini
SEEDGEN_INFER_MODEL=openai/gpt-5.1
GEN_MODEL_LIST=openai/gpt-5-mini,openai/gpt-5.1
OSSFUZZ_PATH=/workspaces/oss-fuzz-harnessagent
PROJECT=libxml2
HARNESSNAME=html
EOF
```

And the one-shot generation.

```
# pull the latest image
docker pull ghcr.io/emptyiscolor/sunflower-seedmind:latest

# the corpus will be save under /var/tmp/corpus
docker run -it \
  --env-file .env \
  --privileged \
  --entrypoint=/entrypoint_harnessagent.sh \
  --rm \
  -v $PWD/entrypoint_harnessagent.sh:/entrypoint_harnessagent.sh \
  -v /var/tmp/corpus:/workspaces/corpus \
  -v /mnt/ssd/fuzzing/oss-fuzz-private:/workspaces/oss-fuzz-harnessagent \
  ghcr.io/emptyiscolor/sunflower-seedmind:latest
```