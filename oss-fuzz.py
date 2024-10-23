# oss-fuzz.py
# Run SeedGen on an OSS-Fuzz project
# Usage: python3 oss-fuzz.py [--root path/to/oss_fuzz] <project_name> <harness_binary>

import itertools
import os
import sys
import argparse
import yaml
import subprocess

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
        default=0.1,
        help="Maximum budget of LLM usages, default is $0.1",
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


# Compile the project, the artifacts will be stored in .tmp/<project_name>/out
def compile_project(root, project_name, project_config):
    dockerfile_path = os.path.join(
        root, "projects", project_name, "Dockerfile")
    if not os.path.exists(dockerfile_path):
        raise FileNotFoundError("Dockerfile not found in project directory")
    if subprocess.run(["docker", "--version"]).returncode != 0:
        raise FileNotFoundError("Docker not found on the host machine")

    project_dir = os.path.join(".tmp", project_name)

    # check if project_dir/out exists, if so, we don't need to compile the project again
    if os.path.exists(os.path.join(project_dir, "out")):
        print(f"[*] Project '{project_name}' already compiled, skipping")
        return

    os.makedirs(project_dir, exist_ok=True)
    os.makedirs(os.path.join(project_dir, "out"), exist_ok=True)
    os.makedirs(os.path.join(project_dir, "work"), exist_ok=True)
    os.makedirs(os.path.join(project_dir, "shared"), exist_ok=True)

    project_dir = os.path.abspath(project_dir)
    print(f"[+] Project directory: {project_dir}")

    docker_image_name = f"oss-fuzz-build-{project_name}"
    build_command = [
        "docker",
        "build",
        "-t",
        docker_image_name,
        ".",
    ]
    subprocess.run(build_command, check=True,
                   cwd=os.path.dirname(dockerfile_path))

    # Run the Docker container with the project image
    # Mount the `out` and `work` directories to the temporary directory
    mount_configs = {
        "/out": f"{project_dir}/out",
        "/work": f"{project_dir}/work",
        "/shared": f"{project_dir}/shared",
        "/clang-argus": get_prebuilt_binary_path("argus"),
        "/clang-argus++": get_prebuilt_binary_path("argus"),
        "/libcallgraph_rt.a": get_prebuilt_binary_path("libcallgraph_rt.a"),
        "/FineIWillDoItMyselfPass.so": get_prebuilt_binary_path("FineIWillDoItMyselfPass.so"),
    }
    mount_commands = list(
        itertools.chain.from_iterable(
            ("-v", f"{src}:{dest}") for dest, src in mount_configs.items()
        )
    )
    # Setup the environment variables
    environment_configs = {
        "FUZZING_LANGUAGE": project_config["language"],
        "CC": "/clang-argus",
        "CXX": "/clang-argus++",
        "ADD_RUNTIME": "1",
        "BANDFUZZ_RUNTIME": "libcallgraph_rt.a",  # linking runtime to the target
        "BANDFUZZ_OPT": "0",  # disable optimization (-O0)
        "ADD_ADDITIONAL_PASSES": "FineIWillDoItMyselfPass.so",
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
    subprocess.run(run_command, check=True, stdout=subprocess.PIPE)

# Start the daemon in container


def start_daemon(root, project_name, project_config) -> tuple[str, str]:
    project_dir = os.path.abspath(os.path.join(".tmp", project_name))

    # double check if project_dir/out exists, if not, the project is not compiled
    if not os.path.exists(os.path.join(project_dir, "out")):
        raise FileNotFoundError(f"Project '{project_name}' not compiled")

    docker_image_name = f"oss-fuzz-build-{project_name}"

    # Run the Docker container with the project image
    # Mount the `out` and `work` directories to the temporary directory
    mount_configs = {
        "/out": f"{project_dir}/out",
        "/work": f"{project_dir}/work",
        "/shared": f"{project_dir}/shared",
        "/clang-argus": get_prebuilt_binary_path("argus"),
        "/clang-argus++": get_prebuilt_binary_path("argus"),
        "/libcallgraph_rt.a": get_prebuilt_binary_path("libcallgraph_rt.a"),
        "/FineIWillDoItMyselfPass.so": get_prebuilt_binary_path("FineIWillDoItMyselfPass.so"),
        "/seedgen-injected": get_prebuilt_binary_path("seedgen-injected"),
        "/seedgen.sh": get_prebuilt_binary_path("seedgen.sh"),
    }
    mount_commands = list(
        itertools.chain.from_iterable(
            ("-v", f"{src}:{dest}") for dest, src in mount_configs.items()
        )
    )
    # Setup the environment variables
    environment_configs = {
        "FUZZING_LANGUAGE": project_config["language"],
        "CC": "/clang-argus",
        "CXX": "/clang-argus++",
        "ADD_RUNTIME": "1",
        "BANDFUZZ_RUNTIME": "libcallgraph_rt.a",  # linking runtime to the target
        "BANDFUZZ_OPT": "0",  # disable optimization (-O0)
        "ADD_ADDITIONAL_PASSES": "FineIWillDoItMyselfPass.so",
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
    return project_name, container_id


def get_prebuilt_binary_path(binary_name):
    binary_path = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), "prebuilt", binary_name
    )
    if not os.path.exists(binary_path):
        raise FileNotFoundError(f"{binary_name} not found")
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
        runtime_id, container_id = start_daemon(
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
