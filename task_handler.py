import argparse
import os
import requests
import tarfile
import shutil
import subprocess
import json
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
from sqlalchemy.dialects.postgresql import JSON  # For PostgreSQL; for SQLite you can use TEXT instead
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
    runtime_id = max([int(d) for d in os.listdir(artifacts_dir) if d.isdigit()])
    project_dir = os.path.join(artifacts_dir, str(runtime_id))
    shutil.copytree(project_dir, os.path.join(task_dir, "result"))


Base = declarative_base()

class SeedRecord(Base):
    __tablename__ = "seeds"

    # Internal primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Required fields
    task_id      = Column(String, nullable=False)
    created_at   = Column(DateTime, nullable=False, default=datetime.now(UTC))
    path         = Column(String, nullable=False)  # path/to/seed_xxx.tar.gz
    harness_name = Column(String, nullable=False)
    fuzzer       = Column(String, nullable=False)  # e.g., wild / seedgen / prime / etc.
    coverage     = Column(String, nullable=False)  # e.g., "69%"

    # Optional metric JSON
    metric       = Column(JSON, nullable=True)  # store arbitrary JSON


def save_result_to_db(task: TaskData, storage_dir: str, database_url: str):
    """
    Save the results of a TaskData to a DB pointed to by database_url,
    storing seeds in storage_dir.
    """
    engine = create_engine(database_url, echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db_session = SessionLocal()

    task_result_dir = os.path.abspath(os.path.join(".tmp", "tasks", str(task.task_id), "result"))

    # Peek into the result directory
    root, dirs, files = next(os.walk(task_result_dir))
    
    # Filter out the unwanted subdirs
    dirs = [d for d in dirs if d not in ("out", "work", "shared")]
    
    try:
        for subdir in dirs:
            # Compress and copy seeds to shared volume
            seed_dir = os.path.join(task_result_dir, subdir, "seeds")
            seedgen_storage_dir = os.path.join(storage_dir, "seedgen", str(task.task_id))
            os.makedirs(seedgen_storage_dir, exist_ok=True)
            seed_tar_gz_path = os.path.join(seedgen_storage_dir, f"seedgen_{task.task_id}_{subdir}.tar.gz")
            with tarfile.open(seed_tar_gz_path, "w:gz") as tar:
                tar.add(seed_dir, arcname=".")

            # Create DB record
            new_seed_record = SeedRecord(
                task_id=str(task.task_id),  # Ensure string
                created_at=datetime.utcnow(),
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
        pika.ConnectionParameters(host=rabbitmq_host)
    )
    channel = connection.channel()

    # 2. Make sure the queue exists (idempotent)
    # channel.queue_declare(
    #     queue=queue_name,
    #     durable=True
    # )

    # 3. Define a callback to process messages
    def callback(ch, method, properties, body):
        try:
            data_dict = json.loads(body)

            # Convert the JSON/dict to TaskData
            task = TaskData(
                task_id=data_dict["task_id"],
                task_type=data_dict["task_type"],
                project_name=data_dict["project_name"],
                focus=data_dict["focus"],
                repo=data_dict["repo"],
                fuzz_tooling=data_dict["fuzzing_tooling"],
                diff=data_dict["diff"]
            )

            print(f"[*] Received task: {task}")

            # Handle the task (extract, run seedgen)
            run_seedgen_for_task(task)

            # Write result to database
            save_result_to_db(task, storage_dir, database_url)

            # Acknowledge the message
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            # If there's a parsing error or missing field, handle it here
            print(f"[!] Failed to parse or process task: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    # 4. Start consuming messages
    channel.basic_consume(
        queue=queue_name,
        on_message_callback=callback
    )

    print("[*] Listening for tasks. Press CTRL+C to exit.")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        print("[*] Stopping consumer...")
        channel.stop_consuming()
        connection.close()


if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="RabbitMQ seedgen consumer")
    parser.add_argument(
        "--rabbitmq_host",
        default="localhost",
        help="RabbitMQ host (default: localhost)"
    )
    parser.add_argument(
        "--queue_name",
        default="seedgen_queue",
        help="RabbitMQ queue name (default: seedgen_queue)"
    )
    parser.add_argument(
        "--database_url",
        default="postgresql://user:password@localhost/mydatabase",
        help="Database URL (default: postgresql://user:password@localhost/mydatabase)"
    )
    parser.add_argument(
        "--storage_dir",
        default="/crs",
        help="Directory path to store seeds and archives (default: /crs)"
    )

    args = parser.parse_args()

    # Start listening for tasks with the given args
    listen_for_tasks(
        rabbitmq_host=args.rabbitmq_host,
        queue_name=args.queue_name,
        database_url=args.database_url,
        storage_dir=args.storage_dir
    )