from aixcc import build_and_run_targets

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
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

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
            # e.g. if 'my_project/foo.c' => top_level is 'my_project'
            root = member.name.split('/')[0]
            if root:  # Make sure it's not empty
                top_level_dirs.add(root)

        # Extract all files
        tar.extractall(path=dest_dir)

    # Optionally remove the tar file after extraction
    os.remove(filename)

    # If there's exactly one top-level directory, return it
    if len(top_level_dirs) == 1:
        return top_level_dirs.pop()

    # Otherwise, we didn't get exactly one top-level dir
    return None


def extract_from_storage(tar_path: str, dest_dir: str) -> str:
    if not tar_path:
        return ""

    # Inspect the tarfile to figure out the top-level directory
    with tarfile.open(tar_path, 'r:gz') as tar:
        top_level_dirs = set()
        for member in tar.getmembers():
            # e.g. if 'my_project/foo.c' => top_level is 'my_project'
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


def run_seedgen_for_task(task: TaskData):
    # Create a directory for this task
    task_dir = os.path.abspath(os.path.join(".tmp", "tasks", str(task.task_id)))
    os.makedirs(task_dir, exist_ok=True)

    extracted_repos = []
    for repo_url in task.repo:
        folder_name = download_and_extract(repo_url, task_dir)
        extracted_repos.append(folder_name)

    fuzz_tooling_dir = download_and_extract(task.fuzz_tooling, task_dir)
    diff_dir = download_and_extract(task.diff, task_dir)

    print("[*] All archives have been downloaded and extracted.")
    print(f"- Task directory: {task_dir}")
    print(f"- Repo directories extracted: {extracted_repos}")
    print(f"- Fuzz tooling extracted into: {fuzz_tooling_dir}")
    print(f"- Diff extracted into: {diff_dir}")

    # Invoke seedgen
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
    __tablename__ = "Seed"

    # This is an internal primary key (auto-increment), optional but recommended
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Your required fields:
    task_id     = Column(String, nullable=False)
    create_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    seed_path   = Column(String, nullable=False)  # e.g., path/to/seed_xxx.tar.gz
    harness     = Column(String, nullable=False)
    fuzzer      = Column(String, nullable=False)  # wild / seedgen / prime / etc.
    coverage    = Column(String, nullable=False)  # e.g., "69%"

    # Optional metric JSON: 
    # - For PostgreSQL you can use `dialects.postgresql.JSON`
    # - For other DBs you might store as TEXT and parse it yourself
    metrics     = Column(JSON, nullable=True)  # store any arbitrary JSON here


def save_result_to_db(task: TaskData):
    DATABASE_URL = "sqlite:///seed.db"
    engine = create_engine(DATABASE_URL, echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db_session = SessionLocal()

    task_result_dir = os.path.abspath(os.path.join(".tmp", "tasks", str(task.task_id)), "result")

    root, dirs, files = next(os.walk(task_result_dir))
    
    # Filter out the unwanted subdirs
    dirs = [d for d in dirs if d not in ("out", "work", "shared")]
    
    try:
        for subdir in dirs:
            # Compress and copy seeds to shared volume
            seed_dir = os.path.join(task_result_dir, subdir, "seeds")
            seed_tar_gz_path = ""

            # Create DB record
            new_seed_record = SeedRecord(
                task_id=task.task_id,
                create_time=datetime.utcnow(),
                seed_path=seed_tar_gz_path,
                harness=subdir,
                fuzzer="?",
                coverage="69%",
                metrics=None
            )
            db_session.add(new_seed_record)
            db_session.commit()
    except Exception as e:
        db_session.rollback()
        print("Error occurred:", e)
    finally:
        db_session.close()



def listen_for_tasks(
    rabbitmq_host: str = "localhost",
    queue_name: str = "task_queue"
):
    """
    Connect to RabbitMQ, listen for tasks in JSON format on `queue_name`,
    parse the message into a TaskData object, and print it.
    """

    # 1. Connect to RabbitMQ
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(host=rabbitmq_host)
    )
    channel = connection.channel()

    # 2. Make sure the queue exists (this is idempotent)
    channel.queue_declare(queue=queue_name, durable=True)

    # 3. Define a callback to process messages from the queue
    def callback(ch, method, properties, body):
        try:
            # Parse JSON from the message body
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

            # Handle the task and run seedgen
            run_seedgen_for_task(task)

            # Write result to database
            # save_result_to_db(task)

            # Acknowledge the message so RabbitMQ knows it can be removed from the queue
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            # If there's a parsing error or a missing field, handle it here
            print(f"[!] Failed to parse task: {e}")
            # You may want to NACK or requeue the message instead of acknowledging
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    # 4. Start consuming messages, using our callback
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
    listen_for_tasks(
        rabbitmq_host="localhost",
        queue_name="task_queue"
    )
