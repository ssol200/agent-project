from google import genai
from google.genai import types
import os

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", "AIzaSyDgnXOCrVTJ7VIGjFmj6vejXJXauEYIyfg"))

try:
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents="Hello",
        config=types.GenerateContentConfig(
            safety_settings=[
                types.SafetySetting(category="HATE_SPEECH", threshold="OFF")
            ]
        )
    )
    print("Success:", response.text)
except Exception as e:
    print("Error:", repr(e))
