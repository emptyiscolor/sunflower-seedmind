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

import pika

from sqlalchemy import (
    create_engine,
    Column,
    String,
    Integer,
    DateTime,
    Text
)
# For PostgreSQL; for SQLite you can use TEXT instead
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime, UTC

from aixcc import build_and_run_targets


@dataclass
class TaskData:
    task_id: int
    task_type: str
    project_name: str
    focus: str
    repo: List[str]         # A list of URLs to .tar.gz files
    fuzz_tooling: str       # A URL to a .tar.gz file
    diff: str               # Another URL to a .tar.gz file


def download_and_extract(url: str, dest_dir: str) -> str:
    """
    Download a .tar.gz file from the given URL into dest_dir,
    then extract it. Removes the .tar.gz file after extraction.

    Returns
    -------
    str:
        The top-level directory name that was extracted.
        If the tar contains multiple top-level dirs, returns None.
        If the URL is empty/invalid, returns an empty string.
    """
    if not url:
        return ""

    # Ensure the destination directory exists
    os.makedirs(dest_dir, exist_ok=True)

    # Download filename (e.g., https://example.com/foo.tar.gz -> foo.tar.gz)
    filename = os.path.join(dest_dir, os.path.basename(url))

    # Download the file
    with requests.get(url, stream=True) as r:
        r.raise_for_status()  # Raise an HTTPError if status != 200
        with open(filename, 'wb') as f:
            shutil.copyfileobj(r.raw, f)

    # Inspect the tarfile to figure out the top-level directory
    with tarfile.open(filename, 'r:gz') as tar:
        top_level_dirs = set()
        for member in tar.getmembers():
            root = member.name.split('/')[0]
            if root:  # Make sure it's not empty
                top_level_dirs.add(root)

        # Extract all files
        tar.extractall(path=dest_dir)

    # If there's exactly one top-level directory, return it
    if len(top_level_dirs) == 1:
        return top_level_dirs.pop()

    # Otherwise, we didn't get exactly one top-level dir
    return None


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
            root = member.name.split('/')[0]
            if root:  # Make sure it's not empty
                top_level_dirs.add(root)

        # Extract all files
        tar.extractall(path=dest_dir)

    # If there's exactly one top-level directory, return it
    if len(top_level_dirs) == 1:
        return top_level_dirs.pop()

    return None


def run_seedgen_for_task(task: TaskData):
    """
    Given a TaskData, extract the repos, fuzzing_tooling, diff archives
    into a .tmp/tasks/<task_id> folder and run build_and_run_targets.
    """
    # Create a directory for this task
    task_dir = os.path.abspath(os.path.join(
        ".tmp", "tasks", str(task.task_id)))
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

    # Apply the diff files
    if diff_dir:
        diff_files = [f for f in os.listdir(os.path.join(task_dir, diff_dir)) if f.endswith('.patch') or f.endswith('.diff')]
        for diff_file in diff_files:
            diff_file_path = os.path.join(task_dir, diff_dir, diff_file)
            if os.path.exists(diff_file_path):
                apply_diff_command = ["patch", "-p1"]
                with open(diff_file_path, "rb") as patch_file:
                    subprocess.run(apply_diff_command, stdin=patch_file, check=True, cwd=task_dir)
                print(f"[+] Applied diff from {diff_file_path} to {task_dir}")
            else:
                print(f"[!] Diff file {diff_file_path} does not exist")

    # Invoke seedgen (build_and_run_targets from aixcc)
    build_and_run_targets(
        project_name=task.project_name,
        harness_binaries=[],
        src_path=os.path.join(task_dir, task.focus),
        fuzz_tooling=os.path.join(task_dir, fuzz_tooling_dir),
        all=True
    )

    # Copy the result out to task_dir
    artifacts_dir = os.path.abspath(os.path.join(".tmp", task.project_name))
    runtime_id = max([int(d)
                     for d in os.listdir(artifacts_dir) if d.isdigit()])
    project_dir = os.path.join(artifacts_dir, str(runtime_id))
    shutil.copytree(project_dir, os.path.join(task_dir, "result"))


Base = declarative_base()


class SeedRecord(Base):
    __tablename__ = "seeds"

    # Internal primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Required fields
    task_id = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now(UTC))
    path = Column(String, nullable=False)  # path/to/seed_xxx.tar.gz
    harness_name = Column(String, nullable=False)
    # e.g., wild / seedgen / prime / etc.
    fuzzer = Column(String, nullable=False)
    coverage = Column(String, nullable=False)  # e.g., "69%"

    # Optional metric JSON
    metric = Column(JSON, nullable=True)  # store arbitrary JSON


def save_result_to_db(task: TaskData, storage_dir: str, database_url: str):
    """
    Save the results of a TaskData to a DB pointed to by database_url,
    storing seeds in storage_dir.
    """
    engine = create_engine(database_url, echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db_session = SessionLocal()

    task_result_dir = os.path.abspath(os.path.join(
        ".tmp", "tasks", str(task.task_id), "result"))

    # Peek into the result directory
    root, dirs, files = next(os.walk(task_result_dir))

    # Filter out the unwanted subdirs
    dirs = [d for d in dirs if d not in ("out", "work", "shared")]

    try:
        for subdir in dirs:
            # Compress and copy seeds to shared volume
            seed_dir = os.path.join(task_result_dir, subdir, "seeds")
            seedgen_storage_dir = os.path.join(
                storage_dir, "seedgen", str(task.task_id))
            os.makedirs(seedgen_storage_dir, exist_ok=True)
            seed_tar_gz_path = os.path.join(seedgen_storage_dir, f"seedgen_{
                                            task.task_id}_{subdir}.tar.gz")
            with tarfile.open(seed_tar_gz_path, "w:gz") as tar:
                tar.add(seed_dir, arcname=".")

            # Create DB record
            new_seed_record = SeedRecord(
                task_id=str(task.task_id),  # Ensure string
                created_at=datetime.now(UTC),
                path=seed_tar_gz_path,
                harness_name=subdir,
                fuzzer="seedgen",
                coverage=0.6969,
                metric=None
            )
            db_session.add(new_seed_record)
            db_session.commit()
    except Exception as e:
        db_session.rollback()
        print("Error occurred:", e)
    finally:
        db_session.close()


def listen_for_tasks(
    rabbitmq_host: str,
    queue_name: str,
    database_url: str,
    storage_dir: str
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
    # channel.queue_declare(
    #     queue=queue_name,
    #     durable=True
    # )

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
                target=process_task, args=(connection, ch, method, task))
            processing_thread.start()

        except Exception as e:
            print(f"[!] Failed to parse or process task: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def process_task(connection, ch, method, task):
        try:
            run_seedgen_for_task(task)
            save_result_to_db(task, storage_dir, database_url)
            cb = functools.partial(ack_nack_message, ch, method.delivery_tag)
            connection.add_callback_threadsafe(cb)
        except Exception as e:
            print(f"[!] Error processing task {task.task_id}: {e}")
            print(traceback.format_exc())
            cb = functools.partial(ack_nack_message, ch,
                                   method.delivery_tag, True)
            connection.add_callback_threadsafe(cb)

    def ack_nack_message(channel, delivery_tag, nack=False):
        if channel.is_open:
            if nack:
                channel.basic_nack(delivery_tag, requeue=False)
            else:
                channel.basic_ack(delivery_tag)
        else:
            raise pika.exceptions.StreamLostError

    # 4. Start consuming messages
    channel.basic_qos(prefetch_count=1)
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
    storage_dir = os.environ.get("STORAGE_DIR", "/crs")

    # Optional: Print configurations for debugging purposes
    print("Configuration:")
    print(f"  RabbitMQ Host: {rabbitmq_host}")
    print(f"  Queue Name: {queue_name}")
    print(f"  Database URL: {database_url}")
    print(f"  Storage Directory: {storage_dir}")

    # Start listening for tasks with the given args
    listen_for_tasks(
        rabbitmq_host=rabbitmq_host,
        queue_name=queue_name,
        database_url=database_url,
        storage_dir=storage_dir
    )
