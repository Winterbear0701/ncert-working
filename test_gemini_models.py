"""
Test script to check available Gemini 2.0 models
"""
import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

print("Testing Gemini 2.0 models...\n")

models_to_test = [
    'gemini-2.0-flash-001',
    'gemini-2.0-flash',
    'gemini-2.0-flash-exp',
    'gemini-1.5-flash',
    'gemini-1.5-flash-latest',
]

for model_name in models_to_test:
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content("Hello, respond with 'OK'")
        print(f"✅ {model_name}: {response.text[:20]}")
    except Exception as e:
        print(f"❌ {model_name}: {str(e)[:80]}")

print("\n📋 Available models from API:")
for m in genai.list_models():
    if 'gemini' in m.name.lower() and 'generateContent' in m.supported_generation_methods:
        print(f"  - {m.name}")
