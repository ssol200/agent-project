from google import genai
from google.genai import types
import os

client = genai.Client(api_key="AIzaSyDgnXOCrVTJ7VIGjFmj6vejXJXauEYIyfg")

try:
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents="Please output a JSON",
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1
        )
    )
    print("Success:", response.text)
except Exception as e:
    print("Error:", repr(e))
