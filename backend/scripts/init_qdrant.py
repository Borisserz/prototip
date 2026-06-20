import os
from pathlib import Path
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from qdrant_client import models
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_qdrant import QdrantVectorStore
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import FastEmbedSparse, RetrievalMode

def init_qdrant():
    docs_dir = Path(__file__).parent.parent / "data" / "docs"
    print(f"Loading documents from {docs_dir}")
    
    # Load all markdown and text files
    documents = []
    for filepath in docs_dir.glob("*.md"):
        loader = TextLoader(str(filepath))
        documents.extend(loader.load())
    for filepath in docs_dir.glob("*.txt"):
        loader = TextLoader(str(filepath))
        documents.extend(loader.load())
        
    print(f"Loaded {len(documents)} documents.")
    
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "\n", ".", " ", ""]
    )
    chunks = text_splitter.split_documents(documents)
    print(f"Split into {len(chunks)} chunks.")
    
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    
    # Connect to Qdrant
    # Assuming Qdrant is running via Docker on localhost:6333
    client = QdrantClient("localhost", port=6333)
    
    collection_name = "knowledge_base"
    
    # Recreate collection
    if client.collection_exists(collection_name):
        client.delete_collection(collection_name)
        
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        # Prepare for Sparse vectors
        sparse_vectors_config={"sparse": models.SparseVectorParams()}
    )
    
    # Initialize Sparse Embeddings (BM25)
    sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")

    print("Uploading chunks to Qdrant with Hybrid Search...")
    QdrantVectorStore.from_documents(
        chunks,
        embeddings,
        sparse_embedding=sparse_embeddings,
        retrieval_mode=RetrievalMode.HYBRID,
        url="http://localhost:6333",
        collection_name=collection_name,
        force_recreate=True,
    )
    print("Done! Knowledge base is ready.")

if __name__ == "__main__":
    init_qdrant()
