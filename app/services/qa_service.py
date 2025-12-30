# app/services/qa_service.py
from sqlalchemy.orm import Session
from app.core.config import settings
from app import models
from typing import List
import numpy as np
import openai

openai.api_key = settings.OPENAI_API_KEY

class QAService:
    def __init__(self, db: Session):
        self.db = db

    def _cos_similarities(self, query_vector, vectors):
        # simple numpy cosine similarity
        a = np.array(vectors)
        q = np.array(query_vector)
        # normalize
        a_norm = a / np.linalg.norm(a, axis=1, keepdims=True)
        q_norm = q / np.linalg.norm(q)
        sims = (a_norm @ q_norm).tolist()
        return sims

    def answer_question(self, case_id: int, question: str):
        # 1) embed question
        resp = openai.Embedding.create(model="text-embedding-3-small", input=question)
        q_vec = resp["data"][0]["embedding"]
        # 2) fetch embeddings for case
        embeddings = self.db.query(models.embedding.Embedding).join(models.case_file.CaseFile).filter(models.case_file.CaseFile.case_id==case_id).all()
        if not embeddings:
            return None
        vectors = [e.vector for e in embeddings]
        sims = self._cos_similarities(q_vec, vectors)
        # pick top N
        top_idx = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)[:5]
        context = "\n\n".join([embeddings[i].chunk_text for i in top_idx])
        # 3) call chat completion with context
        prompt = f"Use the context below to answer the question.\n\nContext:\n{context}\n\nQuestion: {question}\n\nAnswer concisely:"
        completion = openai.ChatCompletion.create(model="gpt-4o-mini", messages=[{"role":"user","content":prompt}], max_tokens=300)
        answer = completion.choices[0].message.content.strip()
        sources = [embeddings[i].id for i in top_idx]
        return {"answer": answer, "source_chunks": sources}
