"""Chat models configured from environment variables.

MODEL_* and OCR_* point to OpenAI-compatible endpoints (e.g. Albert API),
so both models are initialized with model_provider="openai".
"""

import os

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

load_dotenv()


def _init_model(name_env: str, api_key_env: str, base_url_env: str) -> BaseChatModel:
    return init_chat_model(
        model=os.environ[name_env],
        model_provider="openai",
        api_key=os.environ.get(api_key_env),
        base_url=os.environ.get(base_url_env),
    )


model = _init_model("MODEL_NAME", "MODEL_API_KEY", "MODEL_BASE_URL")
ocr_model = _init_model("OCR_NAME", "OCR_API_KEY", "OCR_BASE_URL")
