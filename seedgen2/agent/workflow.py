# agent/workflow.py

# Main workflow of SeedGen2
# Connect each subgraph to the main workflow

from langchain_openai import ChatOpenAI
from utils.singleton import singleton


LITELLM_BASE_URL = "https://litellm.mudd.cc"
LITELLM_KEY = "sk-whexy"


@singleton
class SeedGen2KnowledgeableModel:
    def __init__(self):
        self.model = ChatOpenAI(
            model="gpt-4o", base_url=LITELLM_BASE_URL, api_key=LITELLM_KEY)

        self.json_model = self.model.bind(
            response_format={"type": "json_object"}
        )


@singleton
class SeedGen2GenerativeModel:
    def __init__(self):
        self.model = ChatOpenAI(
            model="o1-preview", base_url=LITELLM_BASE_URL, api_key=LITELLM_KEY)

        self.json_model = self.model.bind(
            response_format={"type": "json_object"}
        )


@singleton
class SeedGen2RefinerModel:
    def __init__(self):
        self.model = ChatOpenAI(
            model="qwen", base_url=LITELLM_BASE_URL, api_key=LITELLM_KEY)

        self.json_model = None  # qwen does not support json mode


def build_main_workflow():
    pass


def seedgen2():
    pass
