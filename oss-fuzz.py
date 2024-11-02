# oss-fuzz.py
# Run SeedGen on an OSS-Fuzz project
# Usage: python3 oss-fuzz.py [--root path/to/oss_fuzz] <project_name> <harness_binary>

import itertools
import os
import sys
import argparse
import yaml
import subprocess
import shutil

from seedgen import source, workflow


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run SeedGen on an OSS-Fuzz project")
    parser.add_argument("project_name", type=str,
                        help="Name of the OSS-Fuzz project")
    parser.add_argument(
        "harness_binaries",
        type=str,
        nargs="+",
        help="Name of the fuzz target binaries. These binaries should be present in the `out` directory of the OSS-Fuzz project",
    )
    parser.add_argument(
        "--root",
        type=str,
        default="oss-fuzz",
        help="Path to the OSS-Fuzz root directory",
    )
    parser.add_argument(
        "--level",
        type=int,
        default=5,
        help="Maximum level of the callgraph to be generated, default is 5",
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=1,
        help="Maximum budget of LLM usages, default is $1",
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


def print_project_info(project_name, project_config):
    print("[+] Running SeedGen on OSS-Fuzz project: %s" % project_name)

    # Describe the project with a fancy banner
    print("\n" + "=" * 50)
    print("Project Name: %s" % project_name)
    print("Homepage: %s" % project_config.get("homepage", "N/A"))
    print("Main Repo: %s" % project_config.get("main_repo", "N/A"))
    print("Language: %s" % project_config["language"])
    print("=" * 50 + "\n")


# Compile the project, the artifacts will be stored in .tmp/cache/<project_name>/out
def compile_project(root, project_name, project_config):
    dockerfile_path = os.path.join(
        root, "projects", project_name, "Dockerfile")
    if not os.path.exists(dockerfile_path):
        raise FileNotFoundError("Dockerfile not found in project directory")
    if subprocess.run(["docker", "--version"]).returncode != 0:
        raise FileNotFoundError("Docker not found on the host machine")

    cache_dir = os.path.join(".tmp", "cache", project_name)
    os.makedirs(cache_dir, exist_ok=True)

    # check if project_dir/out exists, if so, we don't need to compile the project again
    if os.path.exists(os.path.join(cache_dir, "out")):
        print(f"[*] Project '{project_name}' already compiled, skipping")
        return

    os.makedirs(os.path.join(cache_dir, "out"))
    os.makedirs(os.path.join(cache_dir, "work"))

    cache_dir = os.path.abspath(cache_dir)
    print(f"[+] Project directory: {cache_dir}")

    docker_image_name = f"oss-fuzz-build-{project_name}"
    build_command = [
        "docker",
        "build",
        "-t",
        docker_image_name,
        ".",
    ]

    # print the command for debugging
    print(f"[+] Running command: {' '.join(build_command)}")

    subprocess.run(build_command, check=True,
                   cwd=os.path.dirname(dockerfile_path))

    # Run the Docker container with the project image
    # Mount the `out` and `work` directories to the temporary directory
    mount_configs = {
        "/out": f"{cache_dir}/out",
        "/work": f"{cache_dir}/work",
        "/clang-argus": get_prebuilt_binary_path("argus"),
        "/clang-argus++": get_prebuilt_binary_path("argus"),
        "/bandld": get_prebuilt_binary_path("bandld"),
        "/libcallgraph_rt.a": get_prebuilt_binary_path("libcallgraph_rt.a"),
        "/SeedMindCFPass.so": get_prebuilt_binary_path("SeedMindCFPass.so"),
    }
    mount_commands = list(
        itertools.chain.from_iterable(
            ("-v", f"{src}:{dest}") for dest, src in mount_configs.items()
        )
    )

    # Setup the environment variables
    environment_configs = {
        # Use Argus to compile the project
        "CC": "/clang-argus",
        "CXX": "/clang-argus++",
        # Argus settings (see https://github.com/whexy/argus for more details)
        "ADD_ADDITIONAL_PASSES": "SeedMindCFPass.so",
        "ADD_RUNTIME": "1",
        "BANDFUZZ_OPT": "0",
        "BANDFUZZ_PROFILE": "1",
        "BANDFUZZ_RUNTIME": "libcallgraph_rt.a",
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
            "docker",
            "run",
            "--privileged",
            "--shm-size=2g",
            "--entrypoint=compile",
        ]
        + mount_commands
        + environment_commands
        + [docker_image_name]
    )

    # print the command for debugging
    print(f"[+] Running command: {' '.join(run_command)}")

    process = subprocess.Popen(
        run_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    for line in process.stdout:
        print(line, end='')
    process.wait()
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, run_command)


# Run the project. All artifacts will be stored in .tmp/<project_name>/<runtime_id>/
def run_project(root, project_name, project_config) -> tuple[str, str]:
    artifacts_dir = os.path.abspath(os.path.join(".tmp", project_name))
    os.makedirs(artifacts_dir, exist_ok=True)

    # determine the runtime id. We get the largest number and plus one
    runtime_ids = [int(d) for d in os.listdir(artifacts_dir) if d.isdigit()]
    runtime_id = max(runtime_ids) + 1 if runtime_ids else 0

    project_dir = os.path.join(artifacts_dir, str(runtime_id))

    # copy files from .tmp/cache/<project_name> to .tmp/<project_name>/<runtime_id>
    shutil.copytree(os.path.join(".tmp", "cache", project_name), project_dir)
    if not os.path.exists(os.path.join(project_dir, "out")):
        raise FileNotFoundError(f"Project '{project_name}' not compiled")

    # create a "shared" folder in project_dir
    os.makedirs(os.path.join(project_dir, "shared"))

    docker_image_name = f"oss-fuzz-build-{project_name}"

    # Run the Docker container with the project image
    # Mount the `out` and `shared` directories to the temporary directory
    mount_configs = {
        "/out": f"{project_dir}/out",
        "/shared": f"{project_dir}/shared",
        "/seedgen-injected": get_prebuilt_binary_path("seedgen-injected"),
        "/getcov": get_prebuilt_binary_path("getcov"),
    }
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

    run_command = (
        [
            "docker",
            "run",
            "-d",
            "--privileged",
            "--shm-size=2g",
            "--entrypoint=/seedgen-injected",
        ]
        + mount_commands
        + environment_commands
        + [docker_image_name]
    )
    result = subprocess.run(run_command, check=True, stdout=subprocess.PIPE)
    container_id = result.stdout.decode().strip()
    return os.path.join(project_name, str(runtime_id)), container_id


def get_prebuilt_binary_path(binary_name):
    binary_path = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), "prebuilt", binary_name
    )
    if not os.path.exists(binary_path):
        raise FileNotFoundError(
            f"{binary_name} not found. Please run `make clean` and then `make` in the root directory to build the tool.")
    return binary_path


def main():
    args = parse_args()
    project_name = args.project_name
    harness_binaries = args.harness_binaries
    budget = args.budget
    root = args.root
    max_level = args.level

    try:
        project_yaml_path = validate_environment(root, project_name)
        project_config = load_project_config(project_yaml_path)
        print_project_info(project_name, project_config)

        # Compile the project
        compile_project(root, project_name, project_config)

        # Start the daemon
        runtime_id, container_id = run_project(
            root, project_name, project_config)

        # Start the agent
        for harness_binary in harness_binaries:
            workflow.start_seedgen(
                runtime_id, container_id, project_name, harness_binary, budget, max_level
            )
    except (FileNotFoundError, ValueError) as e:
        print(f"[-] Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if "container_id" in locals():
            subprocess.run(["docker", "stop", container_id], check=True)


if __name__ == "__main__":
    os.makedirs(".tmp", exist_ok=True)
    # Path to libclang.so, run the script in dev container!
    LIBCLANG_PATH = "/usr/lib/llvm-18/lib/libclang.so"
    source.set_libclang_path(LIBCLANG_PATH)
    main()
