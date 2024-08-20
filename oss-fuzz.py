# oss-fuzz.py
# Run SeedGen on an OSS-Fuzz project
# Usage: python3 oss-fuzz.py [--root path/to/oss_fuzz] <project_name> <harness_binary>

import itertools
import os
import sys
import argparse
import uuid
import yaml
import subprocess

from seedgen import runtime, callgraph, coverage, source, workflow

def parse_args():
    parser = argparse.ArgumentParser(description="Run SeedGen on an OSS-Fuzz project")
    parser.add_argument("project_name", type=str, help="Name of the OSS-Fuzz project")
    parser.add_argument(
        "harness_binary",
        type=str,
        help="Name of the fuzz target binary. This binary should be present in the `out` directory of the OSS-Fuzz project",
    )
    parser.add_argument(
        "--root",
        type=str,
        default="oss-fuzz",
        help="Path to the OSS-Fuzz root directory",
    )
    return parser.parse_args()


def validate_environment(root, project_name):
    if not os.path.exists(root):
        raise FileNotFoundError("OSS-Fuzz root directory not found")

    projects_dir = os.path.join(root, "projects")
    if not os.path.exists(projects_dir):
        raise FileNotFoundError("OSS-Fuzz projects directory not found")

    project_dir = os.path.join(projects_dir, project_name)
    if not os.path.exists(project_dir):
        raise FileNotFoundError(f"OSS-Fuzz project '{project_name}' not found")

    project_yaml_path = os.path.join(project_dir, "project.yaml")
    if not os.path.exists(project_yaml_path):
        raise FileNotFoundError("project.yaml not found in project directory")

    return project_yaml_path


def load_project_config(project_yaml_path):
    with open(project_yaml_path, "r") as f:
        project_config = yaml.safe_load(f)
        if not project_config:
            raise ValueError("project.yaml is empty or invalid")

        if "language" not in project_config:
            raise ValueError("language not found in project.yaml")

        if project_config["language"] not in ["c", "c++"]:
            raise ValueError("Unsupported project language")

        return project_config


def print_project_info(project_name, project_config, harness_binary):
    print("[+] Running SeedGen on OSS-Fuzz project: %s" % project_name)

    # Describe the project with a fancy banner
    print("\n" + "=" * 50)
    print("Project Name: %s" % project_name)
    print("Homepage: %s" % project_config.get("homepage", "N/A"))
    print("Main Repo: %s" % project_config.get("main_repo", "N/A"))
    print("Language: %s" % project_config["language"])
    print("Harness Binary: %s" % harness_binary)
    print("=" * 50 + "\n")

def pretty_print_function_info(func):
    name = func['name']
    coverage = f"Coverage: {func['covered_edges']}/{func['total_edges']}"
    level = f"Level: {func['level']}"
    
    # Determine the width of the box based on the longest line
    max_length = max(len(name), len(coverage), len(level)) + 4  # Adding padding
    
    # Print the top border
    print("┌" + "─" * max_length + "┐")
    
    # Print the function name
    print(f"│ {name.ljust(max_length - 2)} │")
    
    # Print a separator
    print("├" + "─" * max_length + "┤")
    
    # Print the coverage information
    print(f"│ {coverage.ljust(max_length - 2)} │")
    
    # Print another separator
    print("├" + "─" * max_length + "┤")
    
    # Print the level information
    print(f"│ {level.ljust(max_length - 2)} │")
    
    # Print the bottom border
    print("└" + "─" * max_length + "┘")

def run_project(root, project_name, project_config, harness_binary) -> tuple[str, str]:
    # For an OSS-Fuzz project, we need to compile the project in the OSS-Fuzz environment, which is a Docker container

    # First, we need to build the Docker image for the project
    # The Dockerfile for the project is present in the project directory
    # We can use the `docker build` command to build the Docker image

    dockerfile_path = os.path.join(root, "projects", project_name, "Dockerfile")
    if not os.path.exists(dockerfile_path):
        raise FileNotFoundError("Dockerfile not found in project directory")
    # Ensure the Docker daemon is running, and docker is installed on the host machine
    if subprocess.run(["docker", "--version"]).returncode != 0:
        raise FileNotFoundError("Docker not found on the host machine")

    # Assign a runtime id for this run, use UUID
    runtime_id = str(uuid.uuid4())
    print(f"[+] Runtime ID: {runtime_id}")

    # In the temporary directory, create a new directory for this run, with the runtime id, and create `out` and `work` directories
    temp_dir = os.path.join("/tmp", runtime_id)
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(os.path.join(temp_dir, "out"), exist_ok=True)
    os.makedirs(os.path.join(temp_dir, "work"), exist_ok=True)
    os.makedirs(os.path.join(temp_dir, "shared"), exist_ok=True)
    print(f"[+] Temporary directory: {temp_dir}")

    # Build the Docker image for the project
    docker_image_name = f"oss-fuzz-{project_name}"
    build_command = [
        "docker",
        "build",
        "-t",
        docker_image_name,
        ".",
    ]
    subprocess.run(build_command, check=True, cwd=os.path.dirname(dockerfile_path))

    # Run the Docker container with the project image
    # Mount the `out` and `work` directories to the temporary directory
    mount_configs = {
        "/out": f"{temp_dir}/out",
        "/work": f"{temp_dir}/work",
        "/shared": f"{temp_dir}/shared",
        "/argus": get_argus_binary_path(),
        "/argus++": get_argus_binary_path(),
        "/libcallgraph_rt.a": get_tinyrt_object_path(),
        "/seedgen-injected": get_injected_runtime_path(),
    }
    mount_commands = list(itertools.chain.from_iterable(
        ("-v", f"{src}:{dest}") for dest, src in mount_configs.items()
    ))
    # Setup the environment variables
    environment_configs = {
        "FUZZING_LANGUAGE": project_config["language"],
        "CC": "/argus",
        "CXX": "/argus++",
		"BANDFUZZ_RUNTIME": "libcallgraph_rt.a",      # linking runtime to the target
        "BANDFUZZ_FUNCINSTR": "1",                    # enable function-level instrumentation
		"BANDFUZZ_NATIVESANCOV": "1",                 # disable loading our customized sancov.pass
		"DRIVER_PASSTHROUGH": "1",                    # disable driver replacement
		"AFL_USE_ASAN": "1",                          # enable ASAN
    }
    environment_commands = list(itertools.chain.from_iterable(
        ("-e", f"{key}={value}") for key, value in environment_configs.items()
    ))

    run_command = [
        "docker",
        "run",
        "--privileged",
        "--shm-size=2g",
    ] + mount_commands + environment_commands + [docker_image_name]
    subprocess.run(run_command, check=True)

    # Check if the harness binary is present in the `out` directory
    harness_binary_path = os.path.join(temp_dir, "out", harness_binary)
    if not os.path.exists(harness_binary_path):
        raise FileNotFoundError(
            f"Harness binary '{harness_binary}' not found in the 'out' directory"
        )
    
    # Setup an interactive shell in the Docker container
    run_command = [
        "docker",
        "run",
        "-d",
        "-p",
        "9002:9002",
        "--privileged",
        "--shm-size=2g",
        "--entrypoint=/seedgen-injected",
    ] + mount_commands + environment_commands + [docker_image_name]
    result = subprocess.run(run_command, check=True, stdout=subprocess.PIPE)
    container_id = result.stdout.decode().strip()

    return runtime_id, container_id

def start_seedgen(runtime_id: str):
    runtime_folder = os.path.join("/tmp", runtime_id)
    shared_folder = os.path.join(runtime_folder, "shared")

    # Create a /seeds directory in the shared folder
    seeds_folder = os.path.join(shared_folder, "seeds")
    os.makedirs(seeds_folder, exist_ok=True)

    # Start SeedGen in the Docker container
    rt = runtime.SeedGenRuntime()
    rt.wait_until_ready()
    print("[+] SeedGen service is ready, starting the seed generation process...")

    # Locate the harness function
    harness_loc = rt.locate("/out/xml", "LLVMFuzzerTestOneInput")
    if harness_loc is None:
        print("[-] Error: Harness function not found")
        return
    
    harness_filename = harness_loc[0]
    with open(os.path.join(shared_folder, rt.share(harness_filename)), "r") as f:
        harness_code = f.read()
    print(f"[+] Harness function found at {harness_filename}")

    workflow.run_first_round_generation(harness_code)

    # # put a "hi" seed to shared folder
    # with open(os.path.join(seeds_folder, "test_seed"), "w") as f:
    #     f.write("hi")
    
    # calls_report = rt.export_calls("/out/xml", ["/shared/seeds/test_seed"]) # this is a filename in the shared folder
    # if calls_report is None:
    #     print("[-] Error: Failed to export calls")
    #     return
    
    # report_file = os.path.join(shared_folder, calls_report)
    # levels = callgraph.process_call_graph(report_file)
    
    # coverage_report = rt.run("/out/xml", ["/shared/seeds/test_seed"])
    # coverage_info = coverage.parse_libfuzzer_log(coverage_report, levels)
    # print(coverage_info)

    # print("=" * 50 + "\n")

    # for func in coverage_info:
    #     if func["fully_covered"]:
    #         continue

    #     filename, line = func["location"].split(":")

    #     # Step 1: ask rt to share the source file
    #     shared_filename = os.path.join(shared_folder, rt.share(filename))

    #     # Step 2: extract the source code of the function
    #     source_code = source.get_function_source(shared_filename, func["name"])

    #     # Step 3: for each uncovered edge, mark the line in the source code
    #     uncovered_lines = []

    #     for uncovered_pc in func["uncovered_pcs"]:
    #         uncovered_line_number = uncovered_pc.split(":")[1]
    #         uncovered_lines.append(int(uncovered_line_number))
        
    #     pretty_print_function_info(func)
        
    #     # Step 4: print the source code with the uncovered lines marked
    #     if source_code is None:
    #         print(f"[!] Source code not found for function {func['name']}")
    #         # in this case, we can guess the function source from the coverage info
    #         first_known_line = int(line) - 1
    #         last_known_line = max(uncovered_lines + [first_known_line])
    #         print(f"source code (maybe incomplete) from line {first_known_line} to {last_known_line}:")
    #         with open(shared_filename, "r") as f:
    #             lines = f.readlines()
    #             function_source = lines[first_known_line:last_known_line + 10]
    #             for i, line_content in enumerate(function_source, start=first_known_line + 1):
    #                 if i in uncovered_lines:
    #                     print(f"[MISSING]\t{line_content.rstrip()}")
    #                 else:
    #                     print(f"[       ]\t{line_content.rstrip()}")
    #         continue

    #     for line, content in source_code:
    #         if line in uncovered_lines:
    #             print(f"[MISSING]\t{content}")
    #         else:
    #             print(f"[       ]\t{content}")

def get_argus_binary_path():
    # Argus is a compiler wrapper, it should exists in the same directory as this script
    argus_binary_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "prebuilt", "argus")
    if not os.path.exists(argus_binary_path):
        raise FileNotFoundError("Argus binary not found")
    return argus_binary_path

def get_tinyrt_object_path():
    # TinyRT is a runtime library, it should exists in the same directory as this script
    tinyrt_binary_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "prebuilt", "libcallgraph_rt.a")
    if not os.path.exists(tinyrt_binary_path):
        raise FileNotFoundError("TinyRT binary not found")
    return tinyrt_binary_path

def get_injected_runtime_path():
    # Argus is a compiler wrapper, it should exists in the same directory as this script
    injected_binary_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "prebuilt", "seedgen-injected")
    if not os.path.exists(injected_binary_path):
        raise FileNotFoundError("Injected-Runtime binary not found")
    return injected_binary_path

def main():
    args = parse_args()
    project_name = args.project_name
    harness_binary = args.harness_binary
    root = args.root

    try:
        project_yaml_path = validate_environment(root, project_name)
        project_config = load_project_config(project_yaml_path)
        print_project_info(project_name, project_config, harness_binary)
        runtime_id, container_id = run_project(root, project_name, project_config, harness_binary)
        workflow.start_seedgen(runtime_id, harness_binary)
    except (FileNotFoundError, ValueError) as e:
        print(f"[-] Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if 'container_id' in locals():
            subprocess.run(["docker", "stop", container_id], check=True)


if __name__ == "__main__":
    LIBCLANG_PATH = '/usr/lib/llvm-18/lib/libclang.so'
    source.set_libclang_path(LIBCLANG_PATH)
    main()
