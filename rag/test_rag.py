import sys
import logging
from rag.pipeline import RAGSystem

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class RAGTestInterface:
    def __init__(self):
        self.rag = None
        self.session_active = False

    def initialize(self):
        print("\n" + "=" * 70)
        print("RAG Retrieval Testing Interface")
        print("=" * 70)

        try:
            logger.info("Initializing RAG system...")
            self.rag = RAGSystem()

            logger.info("Loading / building index...")
            self.rag.load_or_build()

            logger.info(f"RAG ready. Vectors: {self.rag.total_vectors}")

            self.session_active = True
            self._print_help()

        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            sys.exit(1)

    def _print_help(self):
        print("\nSystem Status: READY")
        print(f"Total Vectors: {self.rag.total_vectors}")
        print("\nCommands:")
        print("  retrieve <query>  → show retrieved chunks")
        print("  context <query>   → show combined context")
        print("  rebuild           → rebuild index")
        print("  exit              → quit")
        print("-" * 70)

    def _handle_retrieval(self, query: str):
        logger.info(f"Retrieving for: {query}")

        chunks = self.rag.retrieve(query)

        if not chunks:
            print("No relevant chunks found.\n")
            return

        print(f"\nRetrieved {len(chunks)} chunks:\n")
        print("-" * 70)

        for i, chunk in enumerate(chunks, 1):
            preview = chunk[:150].replace("\n", " ")
            print(f"[{i}] {preview}...\n")

        print("-" * 70)

    def _handle_context(self, query: str):
        logger.info(f"Building context for: {query}")

        context = self.rag.get_context(query)

        print("\nContext:\n")
        print("-" * 70)
        print(context[:1500] + ("..." if len(context) > 1500 else ""))
        print("-" * 70)

    def run(self):
        self.initialize()

        try:
            while self.session_active:
                user_input = input("\nQuery: ").strip()

                if not user_input:
                    continue

                if user_input.lower() in ("exit", "quit", "q"):
                    print("Session terminated.")
                    break

                if user_input.lower() == "rebuild":
                    logger.info("Rebuilding index...")
                    self.rag.rebuild()
                    print(f"Rebuilt. Vectors: {self.rag.total_vectors}")
                    continue

                if user_input.startswith("retrieve "):
                    self._handle_retrieval(user_input[9:].strip())
                    continue

                if user_input.startswith("context "):
                    self._handle_context(user_input[8:].strip())
                    continue

                print("Unknown command. Use 'retrieve' or 'context'.")

        except KeyboardInterrupt:
            print("\nSession interrupted.")

        finally:
            logger.info("Session closed.")


def main():
    RAGTestInterface().run()


if __name__ == "__main__":
    main()