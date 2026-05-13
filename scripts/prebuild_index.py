import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from rag.pipeline import RAGSystem

def prebuild():
    print(">>> Initializing RAG System...")
    rag = RAGSystem()
    
    print(">>> Building/Loading index...")
    rag.load_or_build()
    
    print(f">>> Done. Total vectors: {rag.total_vectors}")
    print(f">>> Index stored in: {os.path.abspath('data/vector_store')}")

if __name__ == "__main__":
    prebuild()
