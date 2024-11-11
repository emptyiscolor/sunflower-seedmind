# SeedGen2

## Overview

SeedGen2 is a framework designed to generate initial seeds for OSS-Fuzz, enhancing the effectiveness of fuzzing. By leveraging the capabilities of a Large Language Model (LLM), SeedGen2 can create valid seeds and improve them using harness and coverage information.

## Why SeedGen2?

- **Initial Seeds**: Crucial for effective fuzzing.
- **LLM Capabilities**: Utilizes extensive knowledge of file types and code understanding to generate and enhance seeds.
- **Harness and Coverage**: Leverages harness and coverage information to refine seeds.

## Agent

SeedGen2 employs multiple agents to effectively generate seeds. It analyzes project harnesses, documentation, dictionaries (string literals in the program), and source code, utilizing dynamic code coverage and call relationships to facilitate seed generation.

SeedGen2 is designed to be flexible and extensible, allowing for the integration of additional agents to further enhance its capabilities.

## Architecture

SeedGen2 consists of two main components:
1. **Lightweight Runtime**: Compiles and runs the fuzzing harness within an OSS-Fuzz Docker container, collecting dynamic information.
2. **LLM Agent**: Capable of self-reflection and guided by a state machine to ensure tasks are managed effectively and LLM errors are preemptively fixed.

## Getting Started

### Prerequisites
- Docker
- Python 3.x

### Steps

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

## Usage

### Example
To run SeedGen2 for the `libxml2` project with the `xmlreader` harness:
```shell
python3 oss-fuzz.py libxml2 xmlreader
```

## Author

- [Wenxuan Shi](mailto:wenxuan.shi@northwestern.edu)

## Contributing

Contributions are welcome! Please open an issue or submit a pull request if you have any improvements or suggestions.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.