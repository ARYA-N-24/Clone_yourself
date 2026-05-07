import os
from dotenv import load_dotenv
load_dotenv(override=True)
key = os.getenv("OPENAI_API_KEY")
if key:
    print(f"Key found. Starts with: {key[:15]}...")
    print(f"Length: {len(key)}")
else:
    print("Key NOT found in environment.")
