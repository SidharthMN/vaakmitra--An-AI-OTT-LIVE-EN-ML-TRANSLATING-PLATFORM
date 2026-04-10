import sys
import os

# Add current dir to path to import app
sys.path.append(os.getcwd())
from app import translate_text_chunked

long_text = "This is a test. " * 500 # Approx 16 * 500 = 8000 chars
print(f"Testing with text length: {len(long_text)}")

try:
    translated = translate_text_chunked(long_text, target_lang="ml")
    print(f"Success! Translated length: {len(translated)}")
    print(f"Sample: {translated[:100]}...")
except Exception as e:
    print(f"Failed: {e}")
