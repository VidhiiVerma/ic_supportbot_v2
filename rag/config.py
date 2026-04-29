
import os
from pathlib import Path

# ========== DIRECTORIES ==========
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
INDEX_DIR = os.path.join(DATA_DIR, "vector_store")

# Create directories if they don't exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(INDEX_DIR, exist_ok=True)

# ========== CHUNKING ==========
CHUNK_SIZE = 500
CHUNK_OVERLAP = 150

# ========== RETRIEVAL ==========
TOP_K = 5
MIN_SCORE = 0.2

# ========== AZURE OPENAI ==========
AZURE_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_API_VERSION = "2024-12-01-preview"
EMBEDDING_DEPLOYMENT = "text-embedding-3-small"
LLM_DEPLOYMENT = "gpt-5-chat"

# ========== VALIDATION ==========
if not AZURE_API_KEY:
    raise ValueError("AZURE_OPENAI_API_KEY environment variable not set")
if not AZURE_ENDPOINT:
    raise ValueError("AZURE_OPENAI_ENDPOINT environment variable not set")

print(f"RAG Config loaded")
print(f"   Data dir: {DATA_DIR}")
print(f"   Index dir: {INDEX_DIR}")
