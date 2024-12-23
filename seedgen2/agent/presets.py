# agent/workflow.py

# Main workflow of SeedGen2
# Connect each subgraph to the main workflow

from langchain_openai import ChatOpenAI
from seedgen2.utils.singleton import singleton
from pydantic import SecretStr


LITELLM_BASE_URL = "https://litellm.mudd.cc"
LITELLM_KEY = "sk-whexy"


@singleton
class SeedGen2KnowledgeableModel:
    def __init__(self):
        self.model = ChatOpenAI(
            model="o1", base_url=LITELLM_BASE_URL, api_key=SecretStr(LITELLM_KEY))

        self.json_model = self.model.bind(
            response_format={"type": "json_object"}
        )


@singleton
class SeedGen2GenerativeModel:
    # def __init__(self):
    #     self.model = ChatOpenAI(
    #         model="o1-preview", base_url=LITELLM_BASE_URL, api_key=LITELLM_KEY)

    #     self.json_model = self.model.bind(
    #         response_format={"type": "json_object"}
    #     )

    # FOR DEBUG: I replaced it with a faster model gpt-4o
    def __init__(self):
        self.model = ChatOpenAI(
            model="o1", base_url=LITELLM_BASE_URL, api_key=SecretStr(LITELLM_KEY))

        self.json_model = self.model.bind(
            response_format={"type": "json_object"}
        )


@singleton
class SeedGen2RefinerModel:
    def __init__(self):
        self.model = ChatOpenAI(
            model="qwen", base_url=LITELLM_BASE_URL, api_key=SecretStr(LITELLM_KEY))

        self.json_model = None  # qwen does not support json mode


@singleton
class SeedGen2InferModel:
    def __init__(self):
        self.model = ChatOpenAI(
            model="o1", base_url=LITELLM_BASE_URL, api_key=SecretStr(LITELLM_KEY))

        self.json_model = self.model.bind(
            response_format={"type": "json_object"}
        )
