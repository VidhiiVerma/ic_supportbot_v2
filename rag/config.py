import os

# ========== DIRECTORIES ==========
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
INDEX_DIR = os.path.join(DATA_DIR, "vector_store")

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
AZURE_API_VERSION = os.getenv("AZURE_API_VERSION", "2024-12-01-preview")

EMBEDDING_DEPLOYMENT = os.getenv("EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
LLM_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")


# ========== VALIDATION (SAFE) ==========
def validate_config():
    missing = []

    if not AZURE_API_KEY:
        missing.append("AZURE_OPENAI_API_KEY")

    if not AZURE_ENDPOINT:
        missing.append("AZURE_OPENAI_ENDPOINT")

    if missing:
        print(f"[WARNING] Missing env variables: {', '.join(missing)}")
        return False

    return True


# ========== DEBUG ==========
print("RAG Config loaded")
print(f"   Data dir: {DATA_DIR}")
print(f"   Index dir: {INDEX_DIR}")
print(f"   Embedding model: {EMBEDDING_DEPLOYMENT}")
print(f"   LLM model: {LLM_DEPLOYMENT}")