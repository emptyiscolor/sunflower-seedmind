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
from concurrent.futures import ThreadPoolExecutor, as_completed

from seedgen2.seedgen import SeedGenAgent
from seedgen2.seedmini import SeedMiniAgent

from utils.task import TaskData
from utils.redis import get_redis_client
from utils.telemetry import log_seedgen


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


def workdir_from_dockerfile(fuzz_tooling, project_name):
    WORKDIR_REGEX = re.compile(r'\s*WORKDIR\s*([^\s]+)')
    dockerfile_path = os.path.join(
        fuzz_tooling, "projects", project_name, "Dockerfile")
    with open(dockerfile_path) as file_handle:
        lines = file_handle.readlines()
    for line in reversed(lines):  # reversed to get last WORKDIR.
        match = re.match(WORKDIR_REGEX, line)
        if match:
            workdir = match.group(1)
            workdir = workdir.replace('$SRC', '/src')

            if not os.path.isabs(workdir):
                workdir = os.path.join('/src', workdir)

            return os.path.normpath(workdir)
    
    return os.path.join('/src', project_name)


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
    workdir = workdir_from_dockerfile(fuzz_tooling, project_name)
    environment_configs = {
        # Use Argus to compile the project
        "CC": f"{workdir}/42_B3YOND_TOOLS/clang-argus",
        "CXX": f"{workdir}/42_B3YOND_TOOLS/clang-argus++",
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


# Run the project. All artifacts will be stored in .tmp/<project_name>
def run_project(project_dir, fuzz_tooling, image_name, project_name, src_path) -> tuple[str, str]:
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
        workdir = workdir_from_dockerfile(fuzz_tooling, project_name)
        mount_configs[f"{workdir}"] = os.path.abspath(src_path)
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
    return container_id


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


def build_and_run_targets(project_name, src_path, fuzz_tooling, mini=False):
    os.makedirs(".tmp", exist_ok=True)

    project_yaml_path = validate_environment(fuzz_tooling, project_name)
    project_config = load_project_config(project_yaml_path)
    print_project_info(project_name, project_config)

    is_java = project_config["language"] in ["jvm", "java"]

    mock_task = TaskData(
        task_id="test-1234-5678",
        task_type="delta",
        project_name=project_name,
        focus="",
        repo=[],
        fuzz_tooling="",
        diff=""
    )

    if is_java or mini:
        run_mini_mode(project_name, project_config, src_path, fuzz_tooling, task=mock_task)
    else:
        run_full_mode(project_name, project_config, src_path, fuzz_tooling, task=mock_task)


def run_mini_mode(
    project_name,
    project_config,
    src_path,
    fuzz_tooling,
    save_result_func=None,
    task=None,
    database_url="",
    storage_dir=""
):
    project_dir = os.path.abspath(os.path.join(".tmp", "tasks", task.task_id, "seedmini", project_name))
    os.makedirs(project_dir, exist_ok=True)

    oss_fuzz_project_dir = os.path.join(fuzz_tooling, "projects", project_name)
    is_java = project_config["language"] in ["jvm", "java"]

    fuzzers = find_files_with_fuzzer_function(src_path, oss_fuzz_project_dir, is_java)

    harness_binaries = list(fuzzers.keys())
    print(f"[*] Running SeedMini on all fuzzers: {harness_binaries}")

    def process_harness(harness_binary):
        if harness_binary not in fuzzers:
            return
        print(f"[*] Running SeedMini for harness {harness_binary}")
        log_seedgen(task.task_id, "seedmini_started", target=task.project_name, harness_name=harness_binary)

        redis_client = get_redis_client()
        fuzzer_dir = os.path.join(project_dir, harness_binary)
        if os.path.exists(fuzzer_dir):
            if redis_client:
                is_done = redis_client.get(f"seedmini:{task.task_id}:{harness_binary}")
                if is_done == b"done":
                    print(f"[*] Harness {harness_binary} already processed. Skipping.")
                    log_seedgen(task.task_id, "seedmini_skipped_already_processed_harness", target=task.project_name, harness_name=harness_binary)
                    return
                else:
                    print(f"[*] Incomplete fuzzer directory found for harness {harness_binary}, removing it.")
                    log_seedgen(task.task_id, "seedmini_started_reprocessing_incomplete_harness", target=task.project_name, harness_name=harness_binary)
                    shutil.rmtree(fuzzer_dir)
            else:
                shutil.rmtree(fuzzer_dir)
        os.makedirs(fuzzer_dir, exist_ok=True)

        agent = SeedMiniAgent(fuzzer_dir, project_name, harness_binary, fuzzers[harness_binary])
        agent.run()
        log_seedgen(task.task_id, "seedmini_processed_harness", target=task.project_name, harness_name=harness_binary)

        if save_result_func:
            save_result_func(
                database_url,
                storage_dir,
                task,
                harness_binary,
                os.path.join(fuzzer_dir, "seeds"),
                "seedmini"
            )
            print(f"[*] SeedMini: Seeds stored in DB for task {task.task_id} for harness {harness_binary}")
            log_seedgen(task.task_id, "seedmini_stored_to_db", target=task.project_name, harness_name=harness_binary)
            if redis_client:
                redis_client.set(f"seedmini:{task.task_id}:{harness_binary}", "done")

    # Create a thread pool to parallelize the SeedMini execution per harness
    with ThreadPoolExecutor(max_workers=len(harness_binaries) or None) as executor:
        futures = [executor.submit(process_harness, hb) for hb in harness_binaries]

        # Wait for all tasks to complete and handle any exceptions
        errors = []
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                print(f"[!] A harness generated an exception: {exc}")
                log_seedgen(task.task_id, "seedmini_harness_failed", target=task.project_name)
                errors.append(exc)
        if errors:
            raise Exception("One or more harnesses failed")
        print("[*] SeedMini successfully executed on all harnesses")
        log_seedgen(task.task_id, "seedmini_finished", target=task.project_name)


def run_full_mode(
    project_name,
    project_config,
    src_path,
    fuzz_tooling,
    save_result_func=None,
    task=None,
    database_url="",
    storage_dir=""
):
    is_java = project_config["language"] in ["jvm", "java"]

    if is_java:
        # Don't run full seedgen on Java projects
        return
    
    # Compile the project
    image_name, fuzzers = compile_project(fuzz_tooling, project_name, project_config, src_path)
    log_seedgen(task.task_id, "seedgen_full_built_target", target=task.project_name)

    project_dir = os.path.abspath(os.path.join(".tmp", "tasks", task.task_id, "seedgen", project_name))
    os.makedirs(project_dir, exist_ok=True)

    # copy files from <fuzz_tooling>/build/out/<project_name> to .tmp/<project_name>
    shutil.copytree(os.path.join(fuzz_tooling, "build/out", project_name), os.path.join(project_dir, "out"), dirs_exist_ok=True)
    shutil.copytree(os.path.join(fuzz_tooling, "build/work", project_name), os.path.join(project_dir, "work"), dirs_exist_ok=True)
    if not os.path.exists(os.path.join(project_dir, "out")):
        raise FileNotFoundError(f"Project '{project_name}' not compiled")

    # create a "shared" folder in project_dir
    os.makedirs(os.path.join(project_dir, "shared"), exist_ok=True)

    print(f"[*] Running seedgen on all fuzzers: {fuzzers}")
    harness_binaries = fuzzers

    def process_harness(harness_binary):
        if harness_binary not in fuzzers:
            return
        print(f"[*] Running Seedgen for harness {harness_binary}")
        log_seedgen(task.task_id, "seedgen_full_started", target=task.project_name, harness_name=harness_binary)
        try:
            # Start the daemon
            container_id = run_project(
                project_dir, fuzz_tooling, image_name, project_name, src_path)
            redis_client = get_redis_client()
            fuzzer_dir = os.path.join(project_dir, harness_binary)
            if os.path.exists(fuzzer_dir):
                if redis_client:
                    is_done = redis_client.get(f"seedgen:{task.task_id}:{harness_binary}")
                    if is_done == b"done":
                        print(f"[*] Harness {harness_binary} already processed. Skipping.")
                        log_seedgen(task.task_id, "seedgen_full_skipped_already_processed_harness", target=task.project_name, harness_name=harness_binary)
                        return
                    else:
                        print(f"[*] Incomplete fuzzer directory found for harness {harness_binary}, removing it.")
                        log_seedgen(task.task_id, "seedgen_full_started_reprocessing_incomplete_harness", target=task.project_name, harness_name=harness_binary)
                        shutil.rmtree(fuzzer_dir)
                else:
                    shutil.rmtree(fuzzer_dir)
            os.makedirs(fuzzer_dir, exist_ok=True)

            shutil.copytree(os.path.join(project_dir, "out"), os.path.join(fuzzer_dir, "out"), dirs_exist_ok=True)
            shutil.copytree(os.path.join(project_dir, "work"), os.path.join(fuzzer_dir, "work"), dirs_exist_ok=True)
            # get ip address of the seedd container, the container id is container_id
            ip_addr = subprocess.check_output(
                ["docker", "inspect", "-f", "{{.NetworkSettings.IPAddress}}", container_id]).decode().strip()
            agent = SeedGenAgent(fuzzer_dir, ip_addr,
                                project_name, harness_binary)
            agent.run()
        except Exception as e:
            print("Error occurred during full mode:", e)
            if "container_id" in locals():
                print(f"[-] Stopping container {container_id}")
                subprocess.run(["docker", "stop", container_id], check=True)
                subprocess.run(["docker", "rm", container_id], check=True)
            raise
        finally:
            if "container_id" in locals():
                print(f"[-] Stopping container {container_id}")
                subprocess.run(["docker", "stop", container_id], check=True)
                subprocess.run(["docker", "rm", container_id], check=True)

        log_seedgen(task.task_id, "seedgen_full_processed_harness", target=task.project_name, harness_name=harness_binary)

        if save_result_func:
            save_result_func(
                database_url,
                storage_dir,
                task,
                harness_binary,
                os.path.join(fuzzer_dir, "seeds"),
                "seedgen"
            )
            print(f"[*] Seedgen: Seeds stored in DB for task {task.task_id} for harness {harness_binary}")
            log_seedgen(task.task_id, "seedgen_full_stored_to_db", target=task.project_name, harness_name=harness_binary)
            if redis_client:
                redis_client.set(f"seedgen:{task.task_id}:{harness_binary}", "done")

    # Create a thread pool to parallelize the Seedgen execution per harness
    with ThreadPoolExecutor(max_workers=len(harness_binaries) or None) as executor:
        futures = [executor.submit(process_harness, hb) for hb in harness_binaries]

        # Wait for all tasks to complete and handle any exceptions
        errors = []
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                print(f"[!] A harness generated an exception: {exc}")
                log_seedgen(task.task_id, "seedgen_full_harness_failed", target=task.project_name)
                errors.append(exc)
        if errors:
            raise Exception("One or more harnesses failed")
        print("[*] Seedgen Full mode successfully executed on all harnesses")
        log_seedgen(task.task_id, "seedgen_full_finished", target=task.project_name)


def main():
    args = parse_args()
    project_name = args.project_name
    src_path = args.src_path
    fuzz_tooling = args.fuzz_tooling
    mini = args.mini

    build_and_run_targets(project_name, src_path, fuzz_tooling, mini)


if __name__ == "__main__":
    main()
