from google import genai
import os

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", "AIzaSyDgnXOCrVTJ7VIGjFmj6vejXJXauEYIyfg"))

try:
    for model in client.models.list():
        if "flash" in model.name:
            print(model.name)
except Exception as e:
    print("Error:", repr(e))
