import os
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

def clean_qdrant():
    host = os.getenv("QDRANT_HOST", "localhost")
    port = int(os.getenv("QDRANT_PORT", 6333))
    
    print(f"Connecting to Qdrant at {host}:{port}...")
    try:
        client = QdrantClient(host=host, port=port)
        collections = client.get_collections()
        print(f"Current collections: {[c.name for c in collections.collections]}")
        
        # Try to delete the problematic migrations collection if it exists
        # and the test collection
        targets = ["mem0migrations", "mem0_test_crud", "mem0"]
        
        for name in targets:
            try:
                print(f"Attempting to delete collection: {name}")
                client.delete_collection(name)
                print(f"Deleted {name}")
            except Exception as e:
                print(f"Failed to delete {name}: {e}")
                
    except Exception as e:
        print(f"Fatal error connecting/cleaning Qdrant: {e}")

if __name__ == "__main__":
    clean_qdrant()
