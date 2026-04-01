# app/services/embedding_service.py
from app.core.config import settings
from app.core.azure_openai import client
from typing import List

class EmbeddingService:
    def __init__(self):
        pass

    def create_embedding(self, text: str) -> List[float]:
        # single embedding call
        resp = client.embeddings.create(model=settings.AZURE_OPENAI_EMBEDDING_DEPLOYMENT, input=text)
        vector = resp.data[0].embedding
        return vector

    def create_embeddings_for_chunks(self, chunks: List[str]) -> List[List[float]]:
        vectors = []
        for c in chunks:
            v = self.create_embedding(c)
            vectors.append(v)
        return vectors
