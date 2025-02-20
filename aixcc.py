#!/usr/bin/env python
# aixcc.py
# Run SeedGen on an AIxCC generated oss-fuzz project and tooling
# Usage: python3 aixcc.py <project_name> <path_to_fuzz_tooling> <path_to_src_dir> <harness_binary> [--all]

import itertools
import os
import sys
import argparse
import yaml
import subprocess
import shutil
import re
import stat

from seedgen2.seedgen import SeedGenAgent
from seedgen2.seedmini import SeedMiniAgent


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run SeedGen on an OSS-Fuzz project")
    parser.add_argument("project_name", type=str,
                        help="Name of the OSS-Fuzz project")
    parser.add_argument(
        "fuzz_tooling",
        type=str,
        help="Path to the fuzz tooling directory (oss-fuzz)",
    )
    parser.add_argument(
        "src_path",
        type=str,
        help="Path to the local project source directory",
    )
    parser.add_argument(
        "harness_binaries",
        type=str,
        nargs="*",
        help="Name of the fuzz target binaries. These binaries should be present in the `out` directory of the OSS-Fuzz project",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run seedgen on all fuzz target binaries",
    )
    parser.add_argument(
        "--mini",
        action="store_true",
        help="Run seedgen in mini mode",
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

        if project_config["language"] not in ["c", "c++", "java", "jvm"]:
            raise ValueError("Unsupported project language")

        return project_config


def print_project_info(project_name, project_config):
    print("[+] Running SeedGen on OSS-Fuzz project: %s" % project_name)

    # Describe the project with a fancy banner
    print("\n" + "=" * 50)
    print("Project Name: %s" % project_name)
    print("Homepage: %s" % project_config.get("homepage", "N/A"))
    print("Main Repo: %s" % project_config.get("main_repo", "N/A"))
    print("Language: %s" % project_config["language"])
    print("=" * 50 + "\n")


def find_fuzzers(project_out_dir):
    """
    Looks for executables in the given directory 'LLVMFuzzerTestOneInput'.
    Returns a list of matching filenames.
    """

    fuzzers = []

    for filename in os.listdir(project_out_dir):
        filepath = os.path.join(project_out_dir, filename)

        # We only care about regular files that are marked as executable
        if os.path.isfile(filepath) and os.access(filepath, os.X_OK):
            # Use 'strings' to check for the symbol name
            try:
                result = subprocess.run(
                    ["strings", filepath],
                    check=True,
                    capture_output=True,
                    text=True
                )
            except subprocess.CalledProcessError:
                # If 'strings' fails, skip this file
                continue

            # Check if the symbol appears in the output
            if "LLVMFuzzerTestOneInput" in result.stdout:
                fuzzers.append(filename)

    if not fuzzers:
        raise FileNotFoundError("No executables found with the function 'LLVMFuzzerTestOneInput'")
    
    return fuzzers


# Compile the project, the artifacts will be stored in <fuzz_tooling>/build/out/<project_name>/
def compile_project(fuzz_tooling, project_name, project_config, src_path):
    dockerfile_path = os.path.join(
        fuzz_tooling, "projects", project_name, "Dockerfile")
    if not os.path.exists(dockerfile_path):
        raise FileNotFoundError("Dockerfile not found in project directory")
    if subprocess.run(["docker", "ps"]).returncode != 0:
        raise FileNotFoundError("Docker not found on the host machine")
    
    if src_path:
        if not os.path.exists(os.path.abspath(src_path)):
            raise FileNotFoundError(f"Local source path {os.path.abspath(src_path)} doesn't exist")
        src_path = os.path.abspath(src_path)

    cache_dir = os.path.join(".tmp", "cache", project_name)
    os.makedirs(cache_dir, exist_ok=True)

    cache_dir = os.path.abspath(cache_dir)
    print(f"[+] Project directory: {cache_dir}")

    build_command = [
        f"{fuzz_tooling}/infra/helper.py",
        "build_image",
        "--no-pull",
        project_name,
    ]

    # print the command for debugging
    print(f"[+] Running command: {' '.join(build_command)}")

    subprocess.run(build_command, check=True)

    # Copy tooling binaries to local project src directory
    tool_dir = os.path.join(src_path, "42_B3YOND_TOOLS")
    os.makedirs(tool_dir, exist_ok=True)
    tools = {
        os.path.join(tool_dir, "clang-argus"): get_prebuilt_binary_path("argus"),
        os.path.join(tool_dir, "clang-argus++"): get_prebuilt_binary_path("argus"),
        os.path.join(tool_dir, "bandld"): get_prebuilt_binary_path("bandld"),
        os.path.join(tool_dir, "libcallgraph_rt.a"): get_prebuilt_binary_path("libcallgraph_rt.a"),
        os.path.join(tool_dir, "SeedMindCFPass.so"): get_prebuilt_binary_path("SeedMindCFPass.so"),
    }
    for dest, src in tools.items():
        shutil.copyfile(src, dest)
        st = os.stat(dest)
        os.chmod(dest, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # Setup the environment variables
    environment_configs = {
        # Use Argus to compile the project
        "CC": f"/src/{project_name}/42_B3YOND_TOOLS/clang-argus",
        "CXX": f"/src/{project_name}/42_B3YOND_TOOLS/clang-argus++",
        # Argus settings (see https://github.com/whexy/argus for more details)
        "ADD_ADDITIONAL_PASSES": "SeedMindCFPass.so",
        "ADD_RUNTIME": "1",
        "BANDFUZZ_OPT": "0",
        "BANDFUZZ_PROFILE": "1",
        "BANDFUZZ_RUNTIME": "libcallgraph_rt.a",
        "GENERATE_COMPILATION_DATABASE": "1",
        "COMPILATION_DATABASE_DIR": "/out/compilation_database",
        # For OSS-Fuzz projects only:
        "FUZZING_LANGUAGE": project_config["language"],
        # For AIxCC CPs only:
        "CP_HARNESS_EXTRA_CFLAGS": "-fsanitize=fuzzer-no-link",
        "CP_HARNESS_EXTRA_CXXFLAGS": "-fsanitize=fuzzer-no-link",
        "CP_BASE_EXTRA_CFLAGS": "-fsanitize=fuzzer-no-link",
        "CP_BASE_EXTRA_CXXFLAGS": "-fsanitize=fuzzer-no-link",
        "CP_BASE_EXTRA_LDFLAGS": "-fsanitize=fuzzer-no-link",
    }
    environment_commands = list(
        itertools.chain.from_iterable(
            ("-e", f"{key}={value}") for key, value in environment_configs.items()
        )
    )

    run_command = (
        [
            f"{fuzz_tooling}/infra/helper.py",
            "build_fuzzers",
            "--clean",
            project_name,
            src_path,
        ]
        + environment_commands
    )

    # print the command for debugging
    print(f"[+] Running command: {' '.join(run_command)}")

    process = subprocess.Popen(
        run_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, text=True)
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        raise subprocess.CalledProcessError(
            process.returncode, 
            run_command, 
            stdout + stderr
        )

    combined_output = stdout + stderr
    image_name = None
    # Look for "docker build -t "
    match = re.search(r'docker build.*?-t\s+(\S+)', combined_output, re.DOTALL)
    if match:
        image_name = match.group(1)
    else:
        # If not found, look for "=> => naming to "
        match = re.search(r"=> => naming to\s+(\S+)", combined_output)
        if match:
            image_name = match.group(1)

    if not image_name:
        raise ValueError("Can't identify Docker image name from build_fuzzers command")
    
    return image_name, find_fuzzers(os.path.join(fuzz_tooling, "build/out", project_name))


# Run the project. All artifacts will be stored in .tmp/<project_name>/<runtime_id>/
def run_project(fuzz_tooling, image_name, project_name, src_path) -> tuple[str, str]:
    artifacts_dir = os.path.abspath(os.path.join(".tmp", project_name))
    os.makedirs(artifacts_dir, exist_ok=True)

    # determine the runtime id. We get the largest number and plus one
    runtime_ids = [int(d) for d in os.listdir(artifacts_dir) if d.isdigit()]
    runtime_id = max(runtime_ids) + 1 if runtime_ids else 0

    project_dir = os.path.join(artifacts_dir, str(runtime_id))
    os.makedirs(project_dir, exist_ok=True)

    # copy files from <fuzz_tooling>/build/out/<project_name> to .tmp/<project_name>/<runtime_id>
    shutil.copytree(os.path.join(fuzz_tooling, "build/out", project_name), os.path.join(project_dir, "out"))
    shutil.copytree(os.path.join(fuzz_tooling, "build/work", project_name), os.path.join(project_dir, "work"))
    if not os.path.exists(os.path.join(project_dir, "out")):
        raise FileNotFoundError(f"Project '{project_name}' not compiled")

    # create a "shared" folder in project_dir
    os.makedirs(os.path.join(project_dir, "shared"))

    # Run the Docker container with the project image
    # Mount the `out` and `shared` directories to the temporary directory
    mount_configs = {
        "/out": f"{project_dir}/out",
        "/shared": f"{project_dir}/shared",
        "/seedd": get_prebuilt_binary_path("seedd"),
        "/getcov": get_prebuilt_binary_path("getcov"),
    }
    if src_path:
        if not os.path.exists(os.path.abspath(src_path)):
            raise FileNotFoundError(f"Local source path {os.path.abspath(src_path)} doesn't exist")
        mount_configs[f"/src/{project_name}"] = os.path.abspath(src_path)
    mount_commands = list(
        itertools.chain.from_iterable(
            ("-v", f"{src}:{dest}") for dest, src in mount_configs.items()
        )
    )
    # Setup the environment variables
    environment_configs = {
        "ASAN_OPTIONS": "detect_leaks=0",
    }
    environment_commands = list(
        itertools.chain.from_iterable(
            ("-e", f"{key}={value}") for key, value in environment_configs.items()
        )
    )

    docker_command = [
            "docker",
            "run",
            "-d",
            "--privileged",
            "--shm-size=2g",
            "--entrypoint=/seedd",
        ]

    run_command = (
        docker_command
        + mount_commands
        + environment_commands
        + [image_name]
    )
    result = subprocess.run(run_command, check=True, stdout=subprocess.PIPE)
    container_id = result.stdout.decode().strip()
    return project_dir, container_id


def get_prebuilt_binary_path(binary_name):
    binary_path = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), "prebuilt", binary_name
    )
    if not os.path.exists(binary_path):
        raise FileNotFoundError(
            f"{binary_name} not found. Please run `make clean` and then `make` in the root directory to build the tool.")
    return binary_path


def find_files_with_fuzzer_function(src_path, oss_fuzz_project_dir, is_java):
    """
    Iterates over all files under src_path and oss_fuzz_project_dir.
    For non-Java projects, it looks for the string "LLVMFuzzerTestOneInput".
    For Java projects, it looks for the string "fuzzerTestOneInput".
    
    Returns:
        dict: A dictionary where each key is a filename (without its extension) and
              the corresponding value is the file's content.
    """
    import os

    result = {}
    search_dirs = []

    # Validate and add directories if they exist
    if src_path and os.path.exists(src_path):
        search_dirs.append(src_path)
    if oss_fuzz_project_dir and os.path.exists(oss_fuzz_project_dir):
        search_dirs.append(oss_fuzz_project_dir)

    # Determine the target string based on project language
    target_string = "fuzzerTestOneInput" if is_java else "LLVMFuzzerTestOneInput"

    for directory in search_dirs:
        for root, _, files in os.walk(directory):
            for filename in files:
                file_path = os.path.join(root, filename)
                file_base, _ = os.path.splitext(filename)
                try:
                    with open(file_path, "r", errors="replace") as f:
                        content = f.read()
                except Exception:
                    # Skip files that cannot be read as text
                    continue

                if target_string in content:
                    result[file_base] = content

    return result


def build_and_run_targets(project_name, harness_binaries, src_path, fuzz_tooling, all=False, mini=False):
    os.makedirs(".tmp", exist_ok=True)

    project_yaml_path = validate_environment(fuzz_tooling, project_name)
    project_config = load_project_config(project_yaml_path)
    print_project_info(project_name, project_config)

    is_java = project_config["language"] in ["jvm", "java"]

    if is_java or mini:
        run_mini_mode(project_name, project_config, harness_binaries, src_path, fuzz_tooling, all)
    else:
        run_full_mode(project_name, project_config, harness_binaries, src_path, fuzz_tooling, all)


def run_mini_mode(project_name, project_config, harness_binaries, src_path, fuzz_tooling, all=False):
    try:
        artifacts_dir = os.path.abspath(os.path.join(".tmp", project_name))
        os.makedirs(artifacts_dir, exist_ok=True)

        # determine the runtime id. We get the largest number and plus one
        runtime_ids = [int(d) for d in os.listdir(artifacts_dir) if d.isdigit()]
        runtime_id = max(runtime_ids) + 1 if runtime_ids else 0

        project_dir = os.path.join(artifacts_dir, str(runtime_id))
        oss_fuzz_project_dir = os.path.join(fuzz_tooling, "projects", project_name)
        is_java = project_config["language"] in ["jvm", "java"]

        fuzzers = find_files_with_fuzzer_function(src_path, oss_fuzz_project_dir, is_java)

        if all:
            print(f"[*] The flag --all is enabled, running seedgen on all fuzzers: {list(fuzzers.keys())}")
            harness_binaries = list(fuzzers.keys())

        for harness_binary in harness_binaries:
            if harness_binary not in fuzzers:
                continue
            print(f"[*] Running Seedgen Mini for harness {harness_binary}")
            fuzzer_dir = os.path.join(project_dir, harness_binary)
            agent = SeedMiniAgent(fuzzer_dir, project_name, harness_binary, fuzzers[harness_binary])
            agent.run()

    except (FileNotFoundError, ValueError) as e:
        print(f"[-] Error: {e}", file=sys.stderr)
        sys.exit(1)


def run_full_mode(project_name, project_config, harness_binaries, src_path, fuzz_tooling, all=False):
    try:
        # Compile the project
        image_name, fuzzers = compile_project(fuzz_tooling, project_name, project_config, src_path)
        if all:
            print(f"[*] The flag --all is enabled, running seedgen on all fuzzers: {fuzzers}")
            harness_binaries = fuzzers

        # Start the daemon
        project_dir, container_id = run_project(
            fuzz_tooling, image_name, project_name, src_path)

        # Start the agent
        for harness_binary in harness_binaries:
            print(f"[*] Running Seedgen for harness {harness_binary}")
            # make a separate dir for each fuzz binary target
            fuzzer_dir = os.path.join(project_dir, harness_binary)
            os.makedirs(fuzzer_dir, exist_ok=True)
            shutil.copytree(os.path.join(project_dir, "out"), os.path.join(fuzzer_dir, "out"))
            shutil.copytree(os.path.join(project_dir, "work"), os.path.join(fuzzer_dir, "work"))
            # get ip address of the seedd container, the container id is container_id
            ip_addr = subprocess.check_output(
                ["docker", "inspect", "-f", "{{.NetworkSettings.IPAddress}}", container_id]).decode().strip()
            agent = SeedGenAgent(fuzzer_dir, ip_addr,
                                 project_name, harness_binary)
            agent.run()
    except (FileNotFoundError, ValueError) as e:
        print(f"[-] Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if "container_id" in locals():
            print(f"[-] Stopping container {container_id}")
            subprocess.run(["docker", "stop", container_id], check=True)


def main():
    args = parse_args()
    project_name = args.project_name
    harness_binaries = args.harness_binaries
    src_path = args.src_path
    fuzz_tooling = args.fuzz_tooling
    all = args.all
    mini = args.mini

    build_and_run_targets(project_name, harness_binaries, src_path, fuzz_tooling, all, mini)


if __name__ == "__main__":
    main()
