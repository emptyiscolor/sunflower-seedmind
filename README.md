# SeedGen

![](SeedGen.png)

Seed Generation Framework for OSS-Fuzz

## Why Does This Project Exist?

Initial seeds are crucial for effective fuzzing.

Leveraging the extensive knowledge of commonly known file types, a Large Language Model (LLM) can serve as an excellent resource for creating valid seeds. Additionally, the LLM's capability in understanding code and performing logical inference can be utilized to enhance generated seeds by leveraging harness and coverage information.

## Framework Architecture

SeedGen is composed of two main components: a lightweight, portable runtime and an LLM agent. The runtime is responsible for compiling and running the fuzzing harness within an OSS-Fuzz Docker container, as well as collecting coverage information. The LLM agent, on the other hand, possesses the capability for self-reflection.

To manage the LLM agent effectively, we utilize a state machine. This approach ensures that tasks are not entirely dependent on the LLM, allowing the state machine to guide and control its actions, and fix LLM errors in advance to avoid waste.

## Steps

1. **Build the tool**: Run `make` in the root directory to build the tool.

2. **Run the Script**: Execute the following command to run the script:
    ```shell
    python3 oss-fuzz.py <project_name> <harness_name>
    ```
   - **Project Name**: This should match a directory name in `oss-fuzz/projects/`, for example, `libxml2`.
   - **Harness Name**: This should be the name of an executable file found in the `/out` folder after building the project.


## Author Information

- [Wenxuan Shi](mailto:wenxuan.shi@northwestern.edu)