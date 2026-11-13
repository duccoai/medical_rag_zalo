from openai import AsyncOpenAI, OpenAIError

from app.core.config import settings
from app.core.exceptions import AppBaseException
from app.schemas.medical import MedicalResponseSchema


client = AsyncOpenAI(
    api_key=settings.OPENAI_API_KEY.get_secret_value()
    base_url="[https://generativelanguage.googleapis.com/v1beta/openai/](https://generativelanguage.googleapis.com/v1beta/openai/)"
)