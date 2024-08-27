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

from seedgen import source, workflow


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
    temp_dir = os.path.join(".tmp", runtime_id)
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(os.path.join(temp_dir, "out"), exist_ok=True)
    os.makedirs(os.path.join(temp_dir, "work"), exist_ok=True)
    os.makedirs(os.path.join(temp_dir, "shared"), exist_ok=True)

    # get absolute path of the temp directory
    temp_dir = os.path.abspath(temp_dir)
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
        "/seedgen.sh": get_entrypoint_path(),
    }
    mount_commands = list(
        itertools.chain.from_iterable(
            ("-v", f"{src}:{dest}") for dest, src in mount_configs.items()
        )
    )
    # Setup the environment variables
    environment_configs = {
        "FUZZING_LANGUAGE": project_config["language"],
        "CC": "/argus",
        "CXX": "/argus++",
        "BANDFUZZ_RUNTIME": "libcallgraph_rt.a",  # linking runtime to the target
        "BANDFUZZ_FUNCINSTR": "1",  # enable function-level instrumentation
        "BANDFUZZ_NATIVESANCOV": "1",  # disable loading our customized sancov.pass
        "DRIVER_PASSTHROUGH": "1",  # disable driver replacement
        "AFL_USE_ASAN": "1",  # enable ASAN
        "ASAN_OPTIONS": "detect_leaks=0",  # disable leak detection
        "BANDFUZZ_OPT": "0", # disable optimization (-O0)
    }
    environment_commands = list(
        itertools.chain.from_iterable(
            ("-e", f"{key}={value}") for key, value in environment_configs.items()
        )
    )

    run_command = (
        [
            "docker",
            "run",
            "-d",
            "--privileged",
            "--shm-size=2g",
            "--entrypoint=/seedgen.sh",
        ]
        + mount_commands
        + environment_commands
        + [docker_image_name]
    )
    result = subprocess.run(run_command, check=True, stdout=subprocess.PIPE)
    container_id = result.stdout.decode().strip()
    
    # Impossible to do this check here because we change to one-container mode recently
    # Check if the harness binary is present in the `out` directory
    # harness_binary_path = os.path.join(temp_dir, "out", harness_binary)
    # if not os.path.exists(harness_binary_path):
    #     raise FileNotFoundError(
    #         f"Harness binary '{harness_binary}' not found in the 'out' directory"
    #     )

    return runtime_id, container_id


def get_argus_binary_path():
    # Argus is a compiler wrapper, it should exists in the same directory as this script
    argus_binary_path = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), "prebuilt", "argus"
    )
    if not os.path.exists(argus_binary_path):
        raise FileNotFoundError("Argus binary not found")
    return argus_binary_path


def get_tinyrt_object_path():
    # TinyRT is a runtime library, it should exists in the same directory as this script
    tinyrt_binary_path = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), "prebuilt", "libcallgraph_rt.a"
    )
    if not os.path.exists(tinyrt_binary_path):
        raise FileNotFoundError("TinyRT binary not found")
    return tinyrt_binary_path


def get_injected_runtime_path():
    # Argus is a compiler wrapper, it should exists in the same directory as this script
    injected_binary_path = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), "prebuilt", "seedgen-injected"
    )
    if not os.path.exists(injected_binary_path):
        raise FileNotFoundError("Injected-Runtime binary not found")
    return injected_binary_path

def get_entrypoint_path():
    # Argus is a compiler wrapper, it should exists in the same directory as this script
    entrypoint_script_path = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), "prebuilt", "seedgen.sh"
    )
    if not os.path.exists(entrypoint_script_path):
        raise FileNotFoundError("Entrypoint script not found")
    return entrypoint_script_path

def main():
    args = parse_args()
    project_name = args.project_name
    harness_binary = args.harness_binary
    root = args.root

    try:
        project_yaml_path = validate_environment(root, project_name)
        project_config = load_project_config(project_yaml_path)
        print_project_info(project_name, project_config, harness_binary)
        runtime_id, container_id = run_project(
            root, project_name, project_config, harness_binary
        )
        workflow.start_seedgen(runtime_id, container_id, project_name, harness_binary)
    except (FileNotFoundError, ValueError) as e:
        print(f"[-] Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if "container_id" in locals():
            subprocess.run(["docker", "stop", container_id], check=True)


if __name__ == "__main__":
    os.makedirs(".tmp", exist_ok=True)
    LIBCLANG_PATH = "/usr/lib/llvm-18/lib/libclang.so"  # Path to libclang.so, run the script in dev container!
    source.set_libclang_path(LIBCLANG_PATH)
    main()
