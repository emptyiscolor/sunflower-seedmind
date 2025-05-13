# agent/workflow.py

# Main workflow of SeedGen2
# Connect each subgraph to the main workflow

from langchain_openai import ChatOpenAI
from seedgen2.utils.singleton import singleton
from pydantic import SecretStr
from dotenv import load_dotenv
import os

load_dotenv()


class BaseModel:
    def __init__(self, env_var_name, default_model):
        model_name = os.getenv(env_var_name, default_model)
        self.model = ChatOpenAI(
            model=model_name,
            base_url=os.getenv("LITELLM_BASE_URL"),
            api_key=SecretStr(os.getenv("LITELLM_KEY")),
            include_response_headers=True
        )
        # Initialize json_model based on model capabilities
        self.json_model = (
            self.model.bind(response_format={"type": "json_object"})
            if model_name != "qwen"
            else None
        )


class SeedGen2KnowledgeableModel(BaseModel):
    def __init__(self):
        super().__init__("SEEDGEN_KNOWLEDGEABLE_MODEL", "gpt-4o")


class SeedGen2GenerativeModel(BaseModel):
    _instance = None
    _custom_model = None

    @classmethod
    def set_custom_model(cls, model_name):
        cls._custom_model = model_name
        cls._instance = None  # Reset instance to force recreation with new model

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SeedGen2GenerativeModel, cls).__new__(cls)
            if cls._custom_model:
                # Use custom model if set
                model_name = cls._custom_model
                cls._instance.model = ChatOpenAI(
                    model=model_name,
                    base_url=os.getenv("LITELLM_BASE_URL"),
                    api_key=SecretStr(os.getenv("LITELLM_KEY")),
                    include_response_headers=True
                )
                # Initialize json_model based on model capabilities
                cls._instance.json_model = (
                    cls._instance.model.bind(
                        response_format={"type": "json_object"})
                    if model_name != "qwen"
                    else None
                )
                # Skip the __init__ method since we've already initialized
                cls._instance._initialized = True
            else:
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized') or not self._initialized:
            super().__init__("SEEDGEN_GENERATIVE_MODEL", "claude-3.5-sonnet")


class SeedGen2RefinerModel(BaseModel):
    def __init__(self):
        super().__init__("SEEDGEN_REFINER_MODEL", "o1")


class SeedGen2InferModel(BaseModel):
    def __init__(self):
        super().__init__("SEEDGEN_INFER_MODEL", "o3-mini")
