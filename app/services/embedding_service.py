# app/services/embedding_service.py
from app.core.config import settings
import openai
from typing import List

openai.api_key = settings.OPENAI_API_KEY

class EmbeddingService:
    def __init__(self):
        pass

    def create_embedding(self, text: str) -> List[float]:
        # single embedding call
        resp = openai.Embedding.create(model="text-embedding-3-small", input=text)
        vector = resp["data"][0]["embedding"]
        return vector

    def create_embeddings_for_chunks(self, chunks: List[str]) -> List[List[float]]:
        vectors = []
        for c in chunks:
            v = self.create_embedding(c)
            vectors.append(v)
        return vectors
