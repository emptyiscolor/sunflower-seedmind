import os
import traceback
import pika.exceptions
import requests
import tarfile
import shutil
import subprocess
import json
import threading
import functools
from dataclasses import dataclass
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed

import pika

from infra.aixcc import (
    validate_environment,
    load_project_config,
    print_project_info,
    run_mini_mode,
    run_full_mode
)
from utils.task import TaskData
from utils.telemetry import init_opentelemetry
from utils.redis import init_redis
import utils.db as db


def extract_from_storage(tar_path: str, dest_dir: str) -> str:
    """
    Extract a local .tar.gz file (tar_path) into dest_dir, 
    then return the top-level directory if there's exactly one.
    """
    if not tar_path:
        return ""

    with tarfile.open(tar_path, 'r:gz') as tar:
        top_level_dirs = set()
        for member in tar.getmembers():
            root = os.path.normpath(member.name).split('/')[0]
            if root:  # Make sure it's not empty
                top_level_dirs.add(root)

        # Extract all files
        tar.extractall(path=dest_dir)

    # If there's exactly one top-level directory, return it
    if len(top_level_dirs) == 1:
        return top_level_dirs.pop()

    return None


def run_seedgen_for_task(task: TaskData, database_url: str, storage_dir: str):
    """
    Given a TaskData, extract the repos, fuzzing_tooling, diff archives
    into a .tmp/tasks/<task_id> folder and run SeedGen & SeedMini pipelines.
    """
    # Create a directory for this task
    task_dir = os.path.abspath(os.path.join(".tmp", "tasks", str(task.task_id)))
    os.makedirs(task_dir, exist_ok=True)

    # Extract repos
    extracted_repos = []
    for repo_path in task.repo:
        folder_name = extract_from_storage(repo_path, task_dir)
        extracted_repos.append(folder_name)

    # Extract fuzz_tooling
    fuzz_tooling_dir = extract_from_storage(task.fuzz_tooling, task_dir)

    # Extract diff
    diff_dir = extract_from_storage(task.diff, task_dir)

    print("[*] All archives have been extracted.")
    print(f"- Task directory: {task_dir}")
    print(f"- Repo directories extracted: {extracted_repos}")
    print(f"- Fuzz tooling extracted into: {fuzz_tooling_dir}")
    print(f"- Diff extracted into: {diff_dir}")

    # Apply the diff files (code omitted for brevity)
    if diff_dir:
        diff_path = os.path.join(task_dir, diff_dir)
        apply_diff_command = ["patch", "--batch", "--no-backup-if-mismatch", "-p1"]
        if os.path.isfile(diff_path) and (diff_path.endswith('.patch') or diff_path.endswith('.diff')):
            with open(diff_path, "rb") as patch_file:
                subprocess.run(apply_diff_command, stdin=patch_file, check=True, cwd=os.path.join(task_dir, task.focus))
            print(f"[+] Applied diff from {diff_path} to {os.path.join(task_dir, task.focus)}")
        elif os.path.isdir(diff_path):
            diff_files = [f for f in os.listdir(diff_path) if f.endswith('.patch') or f.endswith('.diff')]
            for diff_file in diff_files:
                diff_file_path = os.path.join(diff_path, diff_file)
                if os.path.exists(diff_file_path):
                    with open(diff_file_path, "rb") as patch_file:
                        subprocess.run(apply_diff_command, stdin=patch_file, check=True, cwd=os.path.join(task_dir, task.focus))
                    print(f"[+] Applied diff from {diff_file_path} to {os.path.join(task_dir, task.focus)}")
                else:
                    print(f"[!] Diff file {diff_file_path} does not exist")
        else:
            print(f"[!] The provided diff path {diff_path} is neither a valid file nor a directory.")

    # Prepare for seed generation
    fuzz_tooling = os.path.join(task_dir, fuzz_tooling_dir)
    os.makedirs(".tmp", exist_ok=True)

    project_yaml_path = validate_environment(fuzz_tooling, task.project_name)
    project_config = load_project_config(project_yaml_path)
    print_project_info(task.project_name, project_config)

    # Run SeedMini and SeedGen in parallel using a thread pool
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_mini = executor.submit(
            run_mini_mode,
            task.project_name,
            project_config,
            os.path.join(task_dir, task.focus),
            os.path.join(task_dir, fuzz_tooling_dir),
            save_result_to_db,
            task,
            database_url,
            storage_dir
        )
        future_full = executor.submit(
            run_full_mode,
            task.project_name,
            project_config,
            os.path.join(task_dir, task.focus),
            os.path.join(task_dir, fuzz_tooling_dir),
            save_result_to_db,
            task,
            database_url,
            storage_dir
        )

        errors = []
        for future in as_completed([future_mini, future_full]):
            try:
                future.result()
            except Exception as exc:
                print(f"[!] A seed generation process generated an exception: {exc}")
                errors.append(exc)
        if errors:
            raise Exception("One or more harnesses failed")


def save_result_to_db(
    database_url: str,
    storage_dir: str,
    task: TaskData,
    harness_binary: str,
    seed_dir: str,
    seed_type: str,
    coverage: float = 0,
    metric: str = ""
):
    """
    Save Seedgen/SeedMini result for a harness to a DB pointed to by database_url,
    storing seeds in storage_dir.
    """
    db_session = db.connect_database(database_url)

    try:
        # Compress and copy seeds to shared volume
        seed_storage_dir = os.path.join(
            storage_dir, seed_type, str(task.task_id))
        os.makedirs(seed_storage_dir, exist_ok=True)
        seed_tar_gz_path = os.path.join(seed_storage_dir, f"{seed_type}_{
                                        task.task_id}_{harness_binary}.tar.gz")
        with tarfile.open(seed_tar_gz_path, "w:gz") as tar:
            tar.add(seed_dir, arcname=".")

        # Create DB record
        new_seed_record = db.Seed(
            task_id=str(task.task_id),  # Ensure string
            path=seed_tar_gz_path,
            harness_name=harness_binary,
            fuzzer=seed_type,
            coverage=coverage,
            metric=metric
        )
        db_session.add(new_seed_record)
        db_session.commit()
    except Exception as e:
        db_session.rollback()
        print("Error occurred:", e)
        raise
    finally:
        db_session.close()


def listen_for_tasks(
    rabbitmq_host: str,
    queue_name: str,
    database_url: str,
    storage_dir: str,
    prefetch_count: int
):
    """
    Connect to RabbitMQ, listen for tasks in JSON format on `queue_name`,
    parse the message into a TaskData object, and process it.
    """

    # 1. Connect to RabbitMQ
    connection = pika.BlockingConnection(
        pika.URLParameters(rabbitmq_host)
    )
    channel = connection.channel()

    # 2. Make sure the queue exists (idempotent)
    channel.queue_declare(
        queue=queue_name,
        durable=True
    )

    # 3. Define a callback to process messages
    def callback(ch, method, properties, body, connection):
        try:
            data_dict = json.loads(body)

            diff = data_dict.get("diff", None)

            # Convert the JSON/dict to TaskData
            task = TaskData(
                task_id=data_dict["task_id"],
                task_type=data_dict["task_type"],
                project_name=data_dict["project_name"],
                focus=data_dict["focus"],
                repo=data_dict["repo"],
                fuzz_tooling=data_dict["fuzzing_tooling"],
                diff=diff
            )

            print(f"[*] Received task: {task}")

            # Start a new thread for processing
            processing_thread = threading.Thread(
                target=process_task, args=(connection, ch, method, properties, body, task))
            processing_thread.start()

        except Exception as e:
            print(f"[!] Failed to parse task: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def process_task(connection, ch, method, properties, body, task):
        try:
            run_seedgen_for_task(task, database_url, storage_dir)
            print(f"[*] Seedgen workflow finished for task {task.task_id}")
            cb = functools.partial(ack_nack_message, ch, method.delivery_tag)
            connection.add_callback_threadsafe(cb)
        except Exception as e:
            print(f"[!] Error processing task {task.task_id}: {e}")
            print(traceback.format_exc())

            # Retrieve the current retry count from message headers.
            retry_count = 0
            if properties.headers and "x-retry" in properties.headers:
                retry_count = properties.headers["x-retry"]

            if retry_count < 3:
                new_retry = retry_count + 1
                print(f"[!] Requeuing task {task.task_id}, attempt {new_retry}")
                # Create updated headers with the new retry count.
                new_headers = properties.headers.copy() if properties.headers else {}
                new_headers["x-retry"] = new_retry
                new_props = pika.BasicProperties(headers=new_headers)
                # Republish to the same queue (using queue_name from the parent scope)
                connection.add_callback_threadsafe(
                    lambda: ch.basic_publish(
                        exchange="",
                        routing_key=queue_name,
                        body=body,
                        properties=new_props
                    )
                )
            else:
                print(f"[!] Task {task.task_id} failed after {retry_count} attempts. Not requeuing.")

            # In any case, acknowledge the original message so it is removed from the queue.
            connection.add_callback_threadsafe(
                lambda: ack_nack_message(ch, method.delivery_tag)
            )

    def ack_nack_message(channel, delivery_tag, nack=False):
        if channel.is_open:
            if nack:
                channel.basic_nack(delivery_tag, requeue=False)
            else:
                channel.basic_ack(delivery_tag)
        else:
            raise pika.exceptions.StreamLostError

    # 4. Start consuming messages
    channel.basic_qos(prefetch_count=prefetch_count)
    on_message_callback = functools.partial(callback, connection=connection)
    channel.basic_consume(
        queue=queue_name,
        on_message_callback=on_message_callback
    )

    print("[*] Listening for tasks. Press CTRL+C to exit.")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        print("[*] Stopping consumer...")
        channel.stop_consuming()
        connection.close()


if __name__ == "__main__":
    # Retrieve configuration from environment variables with default values
    rabbitmq_host = os.environ.get("RABBITMQ_HOST", "http://localhost:5672")
    queue_name = os.environ.get("QUEUE_NAME", "seedgen_queue")
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://user:password@localhost/mydatabase"
    )
    redis_url = os.environ.get(
        "REDIS_URL",
        "redis://localhost:6379"
    )
    otel_endpoint = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://localhost:4317"
    )
    storage_dir = os.environ.get("STORAGE_DIR", "/crs")
    prefetch_count = int(os.environ.get("PREFETCH_COUNT", 8))

    # Optional: Print configurations for debugging purposes
    print("Configuration:")
    print(f"  RabbitMQ Host: {rabbitmq_host}")
    print(f"  Queue Name: {queue_name}")
    print(f"  Database URL: {database_url}")
    print(f"  Redis URL: {redis_url}")
    print(f"  OTEL endpoint: {otel_endpoint}")
    print(f"  Storage Directory: {storage_dir}")
    print(f"  Prefetch count: {prefetch_count}")

    init_redis(redis_url)
    init_opentelemetry(otel_endpoint, "seedgen")

    # Start listening for tasks with the given args
    listen_for_tasks(
        rabbitmq_host=rabbitmq_host,
        queue_name=queue_name,
        database_url=database_url,
        storage_dir=storage_dir,
        prefetch_count=prefetch_count
    )
