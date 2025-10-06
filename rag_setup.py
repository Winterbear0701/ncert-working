import chromadb
from chromadb.utils import embedding_functions

# set up Chroma client
client = chromadb.Client()
collection = client.get_or_create_collection("ncert_rag")

# embedding function (using OpenAI)
openai_ef = embedding_functions.OpenAIEmbeddingFunction(api_key="YOUR_OPENAI_API_KEY", model_name="text-embedding-3-small")

# sample content (you’ll replace with real chapter text later)
data = [
    ("chapter_1", "Photosynthesis is the process by which green plants prepare food using sunlight."),
    ("chapter_2", "Water cycle includes evaporation, condensation, and precipitation."),
]

for doc_id, text in data:
    collection.add(documents=[text], ids=[doc_id])

print("✅ ChromaDB setup complete.")
