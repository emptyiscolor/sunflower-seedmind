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
            api_key=SecretStr(os.getenv("LITELLM_KEY"))
        )
        # Initialize json_model based on model capabilities
        self.json_model = (
            self.model.bind(response_format={"type": "json_object"})
            if model_name != "qwen"
            else None
        )


@singleton
class SeedGen2KnowledgeableModel(BaseModel):
    def __init__(self):
        super().__init__("SEEDGEN_KNOWLEDGEABLE_MODEL", "gpt-4o")


@singleton
class SeedGen2GenerativeModel(BaseModel):
    def __init__(self):
        super().__init__("SEEDGEN_GENERATIVE_MODEL", "o1")


@singleton
class SeedGen2RefinerModel(BaseModel):
    def __init__(self):
        super().__init__("SEEDGEN_REFINER_MODEL", "o1")


@singleton
class SeedGen2InferModel(BaseModel):
    def __init__(self):
        super().__init__("SEEDGEN_INFER_MODEL", "o1")
