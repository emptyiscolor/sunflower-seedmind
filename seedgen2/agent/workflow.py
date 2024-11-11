# agent/workflow.py

# Main workflow of SeedGen2
# Connect each subgraph to the main workflow

from langchain_openai import ChatOpenAI


def singleton(cls):
    instances = {}

    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    return get_instance


LITELLM_BASE_URL = "https://litellm.mudd.cc"
LITELLM_KEY = "sk-whexy"


@singleton
class SeedGen2KnowledgeableModel:
    def __init__(self):
        self.model = ChatOpenAI(
            model="gpt-4o", base_url=LITELLM_BASE_URL, api_key=LITELLM_KEY)

        self.json_model = ChatOpenAI(
            model="gpt-4o", base_url=LITELLM_BASE_URL, api_key=LITELLM_KEY, model_kwargs={"response_format": {"type": "json_object"}})


@singleton
class SeedGen2GenerativeModel:
    def __init__(self):
        self.model = ChatOpenAI(
            model="o1-preview", base_url=LITELLM_BASE_URL, api_key=LITELLM_KEY)


@singleton
class SeedGen2RefinerModel:
    def __init__(self):
        self.model = ChatOpenAI(
            model="qwen", base_url=LITELLM_BASE_URL, api_key=LITELLM_KEY)


def build_main_workflow():
    pass


def seedgen2():
    pass
