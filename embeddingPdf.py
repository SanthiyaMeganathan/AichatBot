from pypdf import PdfReader
import chromadb
from chromadb.utils import embedding_functions

reader=PdfReader("Knowledge/Knowledge_base.pdf")
text=" "

for page in reader.pages:
    text+=page.extract_text() + " "

chunk_size=500
overlap=100
chunks=[]

for i in range(0, len(text), chunk_size-overlap):
    chunk = text[i:i+chunk_size]
    chunks.append(chunk)


client =chromadb.PersistentClient(path="./chromadb")

ollama_ef = embedding_functions.OllamaEmbeddingFunction(
    model_name="nomic-embed-text",
    url="http://localhost:11434/api/embeddings",
)

collection = client.get_or_create_collection(
    name="dr_akansha_booking_system_knowledge_base",
    embedding_function=ollama_ef
)


for i,chunk in enumerate(chunks):
    collection.add(
        documents=[chunk],
        ids=[f"chunk_{i}"]

    )

print(f"Success! {len(chunks)} chunks added with the overlap  of {overlap} charecters.")    
