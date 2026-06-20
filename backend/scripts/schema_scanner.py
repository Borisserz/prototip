import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import FastEmbedSparse, QdrantVectorStore, RetrievalMode
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient, models
from qdrant_client.models import Distance, VectorParams

from app.utils.clickhouse_client import ch_client
from core.llm import call_structured


class TableDescription(BaseModel):
    table_name: str = Field(description="Name of the table")
    semantic_description: str = Field(description="Detailed description of what data this table holds, generated from the schema and samples.")
    json_fields: list[str] = Field(description="List of fields that contain nested JSON data, if any.")

def scan_db():
    print("Connecting to ClickHouse...")
    tables_res = ch_client.execute("SHOW TABLES")
    table_names = [row[0] for row in tables_res.result_rows if row[0] != "schema_migrations"]
    
    docs = []
    
    for table_name in table_names:
        print(f"Scanning table: {table_name}...")
        
        # Get columns
        columns = ch_client.execute(f"DESCRIBE TABLE {table_name}")
        schema_text = f"Table: {table_name}\nColumns:\n"
        for row in columns.result_rows:
            schema_text += f"- {row[0]}: {row[1]}\n"
            
        # Get sample rows
        try:
            samples = ch_client.execute(f"SELECT * FROM {table_name} LIMIT 3")
            schema_text += "\nSample Data:\n"
            for row in samples.result_rows:
                schema_text += str(row) + "\n"
        except Exception as e:
            print(f"Could not get samples for {table_name}: {e}")
            
        # Enrich via LLM
        prompt = f"""
        Analyze the following database table schema and sample data. 
        Create a detailed semantic description of what this table is used for in a tax analytics platform.
        Identify any columns that contain nested JSON strings.
        
        Schema and Samples:
        {schema_text}
        """
        
        print(f"Generating LLM semantic description for {table_name}...")
        res = call_structured(prompt, TableDescription)
        
        # Format the context document
        doc_content = f"Table Name: {res.table_name}\n"
        doc_content += f"Semantic Description: {res.semantic_description}\n"
        doc_content += f"JSON Fields: {', '.join(res.json_fields) if res.json_fields else 'None'}\n"
        doc_content += f"Raw Schema:\n{schema_text}"
        
        doc = Document(
            page_content=doc_content,
            metadata={"table": table_name, "type": "schema"}
        )
        docs.append(doc)
        
    if not docs:
        print("No tables found to scan.")
        return

    # Save to Qdrant
    print("Connecting to Qdrant...")
    q_client = QdrantClient("localhost", port=6333)
    collection_name = "db_schema"
    
    try:
        q_client.get_collection(collection_name)
        print(f"Collection {collection_name} exists, recreating...")
        q_client.delete_collection(collection_name)
    except Exception:
        pass
        
    q_client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        sparse_vectors_config={"sparse": models.SparseVectorParams()}
    )
        
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")
    
    print("Uploading enriched schemas to Qdrant...")
    QdrantVectorStore.from_documents(
        docs,
        embeddings,
        sparse_embedding=sparse_embeddings,
        retrieval_mode=RetrievalMode.HYBRID,
        url="http://localhost:6333",
        collection_name=collection_name,
        force_recreate=True,
    )
    print("Semantic layer ingestion complete!")

if __name__ == "__main__":
    scan_db()
