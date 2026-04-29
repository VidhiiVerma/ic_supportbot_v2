import os
from pathlib import Path

from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import AzureOpenAIEmbeddings, AzureChatOpenAI

from rag.config import (
    DATA_DIR,
    INDEX_DIR,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    TOP_K,
    AZURE_API_KEY,
    AZURE_ENDPOINT,
    AZURE_API_VERSION,
    EMBEDDING_DEPLOYMENT,
    LLM_DEPLOYMENT,
)


class RAGSystem:
    def __init__(self):
        self.vector_store = None

        self.embeddings = AzureOpenAIEmbeddings(
            api_key=AZURE_API_KEY,
            azure_endpoint=AZURE_ENDPOINT,
            api_version=AZURE_API_VERSION,
            model=EMBEDDING_DEPLOYMENT,
        )

    # ---------------- LOAD FILES ----------------
    def _load_documents(self):
        docs = []

        for file in Path(DATA_DIR).rglob("*.txt"):
            loader = TextLoader(str(file), encoding="utf-8")
            docs.extend(loader.load())

        return docs

    # ---------------- BUILD INDEX ----------------
    def build(self):
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

        print(f"[RAG] Built with {len(chunks)} chunks")

    # ---------------- ASK ----------------
    def ask(self, query: str):
        if not self.vector_store:
            return {"answer": "RAG not initialized"}

        # 1. Retrieve docs
        docs = self.vector_store.similarity_search(query, k=TOP_K)
        context = "\n\n".join([d.page_content for d in docs])

        # 2. Call LLM
        llm = AzureChatOpenAI(
            api_key=AZURE_API_KEY,
            azure_endpoint=AZURE_ENDPOINT,
            api_version=AZURE_API_VERSION,
            deployment_name=LLM_DEPLOYMENT,
            temperature=0.0,
        )

        response = llm.invoke(f"""
Answer ONLY from the context below.

Context:
{context}

Question:
{query}
""")

        return {
            "answer": response.content,
            "context": context,
        }

    @property
    def total_vectors(self):
        if self.vector_store:
            return self.vector_store.index.ntotal
        return 0