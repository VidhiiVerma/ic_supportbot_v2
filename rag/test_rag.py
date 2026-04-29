
import sys
import logging
from rag.pipeline import RAGSystem

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RAGTestInterface:
    """Professional RAG testing interface"""
    
    def __init__(self):
        self.rag = None
        self.session_active = False
    
    def initialize(self):
        """Initialize RAG system"""
        print("\n" + "=" * 70)
        print("RAG System Testing Interface")
        print("=" * 70)
        
        try:
            logger.info("Initializing RAG system...")
            self.rag = RAGSystem()
            
            logger.info("Building vector store...")
            self.rag.build()
            
            logger.info(
                f"RAG system ready. Indexed vectors: {self.rag.total_vectors}"
            )
            
            self.session_active = True
            self._print_help()
            
        except Exception as e:
            logger.error(f"Failed to initialize RAG system: {e}")
            sys.exit(1)
    
    def _print_help(self):
        """Display help information"""
        print("\nSystem Status: READY")
        print(f"Total Indexed Documents: {self.rag.total_vectors}")
        print("\nSupported Commands:")
        print("  - Question format: [Your question]")
        print("  - Retrieval format: retrieve [your query]")
        print("  - Exit format: quit, exit, or q")
        print("-" * 70)
    
    def _handle_retrieval(self, query):
        """Handle raw document retrieval"""
        logger.info(f"Processing retrieval query: {query}")
        
        hits = self.rag.retrieve(query, top_k=5)
        
        if not hits:
            print("  No relevant documents found for the given query.\n")
            return
        
        print(f"\n  Retrieved {len(hits)} document(s):")
        print("-" * 70)
        
        for index, hit in enumerate(hits, 1):
            source = hit.get("source") or "Unknown"
            if hit.get("sheet_name"):
                source = f"{source} [Sheet: {hit['sheet_name']}]"
            
            relevance_score = hit.get("score", 0.0)
            text_preview = hit.get("text", "")[:120].replace("\n", " ")
            
            print(f"\n  [{index}]")
            print(f"      Source: {source}")
            print(f"      Relevance Score: {relevance_score:.3f}")
            print(f"      Content Preview: {text_preview}...")
        
        print("\n" + "-" * 70 + "\n")
    
    def _handle_question(self, question):
        """Handle QA request"""
        logger.info(f"Processing question: {question}")
        
        result = self.rag.ask(question)
        
        print("\nResponse:")
        print("-" * 70)
        print(result.get("answer", "No answer generated."))
        print("-" * 70)
        
        if result.get("sources"):
            print("\nSource Documents:")
            for source in result["sources"]:
                print(f"  - {source}")
        
        print()
    
    def run(self):
        """Main interactive loop"""
        self.initialize()
        
        try:
            while self.session_active:
                try:
                    user_input = input("\nQuery: ").strip()
                    
                    if not user_input:
                        continue
                    
                    # Exit commands
                    if user_input.lower() in ("quit", "exit", "q"):
                        print("\nSession terminated.")
                        self.session_active = False
                        break
                    
                    # Retrieval mode
                    if user_input.lower().startswith("retrieve "):
                        query = user_input[9:].strip()
                        self._handle_retrieval(query)
                    
                    # QA mode
                    else:
                        self._handle_question(user_input)
                
                except KeyboardInterrupt:
                    print("\n\nSession interrupted by user.")
                    self.session_active = False
                except Exception as e:
                    logger.error(f"Error processing query: {e}")
                    print(f"Error: {e}\n")
        
        finally:
            logger.info("Session closed.")


def main():
    """Entry point"""
    interface = RAGTestInterface()
    interface.run()


if __name__ == "__main__":
    main()