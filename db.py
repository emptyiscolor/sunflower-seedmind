import enum
import os
from sqlalchemy import (
    Column,
    Integer,
    NullPool,
    String,
    BigInteger,
    Boolean,
    Text,
    ForeignKey,
    UniqueConstraint,
    create_engine,
    func,
    Float,
)
from sqlalchemy.orm import relationship, declarative_base, sessionmaker
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy import Enum as SAEnum

Base = declarative_base()


class TaskTypeEnum(enum.Enum):
    full = "full"
    delta = "delta"


class TaskStatusEnum(enum.Enum):
    canceled = "canceled"
    errored = "errored"
    pending = "pending"
    running = "running"
    succeeded = "succeeded"


class SourceTypeEnum(enum.Enum):
    repo = "repo"
    fuzz_tooling = "fuzz_tooling"
    diff = "diff"


class FuzzerTypeEnum(enum.Enum):
    seedgen = "seedgen"
    prime = "prime"
    general = "general"
    directed = "directed"


class SanitizerEnum(enum.Enum):
    ASAN = "ASAN"
    UBSAN = "UBSAN"
    MSAN = "MSAN"


# --- Models ---


class FlywaySchemaHistory(Base):
    __tablename__ = "flyway_schema_history"

    installed_rank = Column(Integer, primary_key=True, nullable=False)
    version = Column(String(50))
    description = Column(String(200), nullable=False)
    type = Column(String(20), nullable=False)
    script = Column(String(1000), nullable=False)
    checksum = Column(Integer)
    installed_by = Column(String(100), nullable=False)
    installed_on = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    execution_time = Column(Integer, nullable=False)
    success = Column(Boolean, nullable=False)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False, unique=True)
    password = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    # A user may create many tasks.
    tasks = relationship("Task", back_populates="user")


class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, nullable=False)
    message_time = Column(BigInteger, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    # A message can be referenced by one or more tasks.
    tasks = relationship("Task", back_populates="message", foreign_keys="[Task.message_id]")
    # A message can also be associated with many SARIF reports.
    sarifs = relationship("Sarif", back_populates="message", foreign_keys="[Sarif.message_id]")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message_id = Column(String, ForeignKey("messages.id"), nullable=False)
    deadline = Column(BigInteger, nullable=False)
    focus = Column(String, nullable=False)
    project_name = Column(String, nullable=False)
    task_type = Column(SAEnum(TaskTypeEnum, name="tasktypeenum"), nullable=False)
    status = Column(SAEnum(TaskStatusEnum, name="taskstatusenum"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="tasks")
    message = relationship("Message", back_populates="tasks", foreign_keys=[message_id])
    sources = relationship("Source", back_populates="task", cascade="all, delete-orphan")
    sarifs = relationship("Sarif", back_populates="task", cascade="all, delete-orphan")
    seeds = relationship("Seed", back_populates="task", cascade="all, delete-orphan")
    bugs = relationship("Bug", back_populates="task", cascade="all, delete-orphan")
    patches = relationship("Patch", back_populates="task", cascade="all, delete-orphan")


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True)
    task_id = Column(String, ForeignKey("tasks.id"), nullable=False)
    sha256 = Column(String(64), nullable=False)
    source_type = Column(SAEnum(SourceTypeEnum, name="sourcetypeenum"), nullable=False)
    url = Column(String, nullable=False)
    path = Column(String)

    # Relationship: each source belongs to a task.
    task = relationship("Task", back_populates="sources")


class Sarif(Base):
    __tablename__ = "sarifs"

    id = Column(String, primary_key=True, nullable=False)
    task_id = Column(String, ForeignKey("tasks.id"), nullable=False)
    message_id = Column(String, ForeignKey("messages.id"), nullable=False)
    sarif = Column(JSONB, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    is_forwarded = Column(Boolean, nullable=False, server_default="false")

    # Relationships
    task = relationship("Task", back_populates="sarifs")
    message = relationship("Message", back_populates="sarifs", foreign_keys=[message_id])


class Seed(Base):
    __tablename__ = "seeds"

    id = Column(Integer, primary_key=True)
    task_id = Column(String, ForeignKey("tasks.id"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    path = Column(Text)
    harness_name = Column(Text)
    fuzzer = Column(SAEnum(FuzzerTypeEnum, name="fuzzertypeenum"))
    coverage = Column(Float)
    metric = Column(JSONB)

    # Each seed is generated for one task.
    task = relationship("Task", back_populates="seeds")


class BugProfile(Base):
    __tablename__ = "bug_profiles"

    id = Column(Integer, primary_key=True)
    sanitizer_bug_type = Column(Text, nullable=False)
    trigger_point = Column(Text, nullable=False)
    summary = Column(Text, nullable=False)

    # A bug profile can be associated (via bug_groups) with many bugs.
    bug_groups = relationship("BugGroup", back_populates="bug_profile", cascade="all, delete-orphan")


class Bug(Base):
    __tablename__ = "bugs"

    id = Column(Integer, primary_key=True)
    task_id = Column(String, ForeignKey("tasks.id"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    architecture = Column(String, nullable=False)
    poc = Column(Text, nullable=False)
    harness_name = Column(Text, nullable=False)
    sanitizer = Column(SAEnum(SanitizerEnum, name="sanitizerenum"))
    sarif_report = Column(JSONB)

    # Relationships
    task = relationship("Task", back_populates="bugs")
    bug_groups = relationship("BugGroup", back_populates="bug", cascade="all, delete-orphan")
    patch_pairs = relationship("PatchPair", back_populates="bug", cascade="all, delete-orphan")


class BugGroup(Base):
    __tablename__ = "bug_groups"

    id = Column(Integer, primary_key=True)
    bug_id = Column(Integer, ForeignKey("bugs.id"), nullable=False)
    bug_profile_id = Column(Integer, ForeignKey("bug_profiles.id"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("bug_id", "bug_profile_id", name="_bug_bugprofile_uc"),)

    # Relationships: each BugGroup connects one Bug with one BugProfile.
    bug = relationship("Bug", back_populates="bug_groups")
    bug_profile = relationship("BugProfile", back_populates="bug_groups")


class Patch(Base):
    __tablename__ = "patches"

    id = Column(Integer, primary_key=True)
    task_id = Column(String, ForeignKey("tasks.id"), nullable=False)
    patch = Column(Text, nullable=False)

    # A patch belongs to one task.
    task = relationship("Task", back_populates="patches")
    patch_pairs = relationship("PatchPair", back_populates="patch", cascade="all, delete-orphan")


class PatchPair(Base):
    __tablename__ = "patch_pairs"

    id = Column(Integer, primary_key=True)
    patch_id = Column(Integer, ForeignKey("patches.id"), nullable=False)
    bug_id = Column(Integer, ForeignKey("bugs.id"), nullable=False)

    # Relationships: links a patch with a bug.
    patch = relationship("Patch", back_populates="patch_pairs")
    bug = relationship("Bug", back_populates="patch_pairs")


def connect_database(database_url):
    engine = create_engine(database_url, poolclass=NullPool)
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()