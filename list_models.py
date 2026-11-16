from google import genai
from app.core.config import settings

client = genai.Client(api_key=settings.GEMINI_API_KEY.get_secret_value())

print(" danh sách model khả dụng:")
for m in client.models.list():
    print(f"- {m.name}")