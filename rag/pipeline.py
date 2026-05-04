import os
from pathlib import Path

from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import AzureOpenAIEmbeddings

from rag.config import (
    DATA_DIR,
    INDEX_DIR,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    TOP_K,
    MIN_SCORE,
    AZURE_API_KEY,
    AZURE_ENDPOINT,
    AZURE_API_VERSION,
    EMBEDDING_DEPLOYMENT,
)
from rag.parser import parse_docx, parse_txt


class RAGSystem:
    def __init__(self):
        self.vector_store = None

        self.embeddings = AzureOpenAIEmbeddings(
            api_key=AZURE_API_KEY,
            azure_endpoint=AZURE_ENDPOINT,
            api_version=AZURE_API_VERSION,
            model=EMBEDDING_DEPLOYMENT,
        )

    # ─────────────────────────────────────────────
    # Load ONLY policy documents (not Excel)
    # ─────────────────────────────────────────────
    def _load_documents(self) -> list[Document]:
        docs = []
        data_path = Path(DATA_DIR)

        for file in data_path.rglob("*"):
            try:
                if file.suffix == ".txt":
                    text = parse_txt(str(file))

                elif file.suffix == ".docx":
                    text = parse_docx(str(file))

                else:
                    continue  # ❌ ignore Excel

                if text.strip():
                    docs.append(Document(
                        page_content=text,
                        metadata={"source": str(file)}
                    ))

            except Exception as e:
                print(f"[RAG] Failed to load {file}: {e}")

        return docs

    # ─────────────────────────────────────────────
    # Build / load index
    # ─────────────────────────────────────────────
    def load_or_build(self):
        index_file = os.path.join(INDEX_DIR, "index.faiss")

        if os.path.exists(index_file):
            print("[RAG] Loading existing index...")
            self.vector_store = FAISS.load_local(
                INDEX_DIR,
                self.embeddings,
                allow_dangerous_deserialization=True,
            )
            print(f"[RAG] Loaded {self.vector_store.index.ntotal} vectors")
            return

        print("[RAG] Building new index...")
        docs = self._load_documents()

        if not docs:
            print("[RAG] No documents found")
            return

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
        )

        chunks = splitter.split_documents(docs)

        self.vector_store = FAISS.from_documents(chunks, self.embeddings)
        self.vector_store.save_local(INDEX_DIR)

        print(f"[RAG] Built {len(chunks)} chunks")

    # ─────────────────────────────────────────────
    # Retrieve ONLY (no LLM here)
    # ─────────────────────────────────────────────
    def retrieve(self, query: str):
        if not self.vector_store:
            return []

        results = self.vector_store.similarity_search_with_score(query, k=TOP_K)

        filtered = []
        for doc, score in results:
            if score < MIN_SCORE:  # 🔥 critical fix
                filtered.append(doc.page_content)

        return filtered

    # ─────────────────────────────────────────────
    # Simple context builder
    # ─────────────────────────────────────────────
    def get_context(self, query: str) -> str:
        chunks = self.retrieve(query)
        return "\n\n".join(chunks)

    @property
    def total_vectors(self):
        if self.vector_store:
            return self.vector_store.index.ntotal
        return 0