# app/services/qa_service.py
from typing import Any, Dict, Optional, List
from datetime import date
import json
import re
import logging

import numpy as np
import openai
from sqlalchemy.orm import Session

from app.core.config import settings
from app import models

openai.api_key = settings.OPENAI_API_KEY

logger = logging.getLogger(__name__)


class QAService:
    def __init__(self, db: Session):
        self.db = db

    # -------------------------
    # Utilities
    # -------------------------
    def _cos_similarities(self, query_vector: List[float], vectors: List[List[float]]) -> List[float]:
        """
        Compute cosine similarities between query_vector and each vector in vectors.
        Handles zero-length vectors safely by using a tiny epsilon.
        """
        a = np.array(vectors, dtype=float)
        q = np.array(query_vector, dtype=float)

        # tiny epsilon to avoid division by zero
        eps = 1e-10
        a_norms = np.linalg.norm(a, axis=1, keepdims=True)
        a_norms[a_norms == 0] = eps
        q_norm = np.linalg.norm(q)
        if q_norm == 0:
            q_norm = eps

        a_norm = a / a_norms
        q_norm = q / q_norm

        sims = (a_norm @ q_norm).tolist()
        return sims

    # -------------------------
    # Q/A with RAG
    # -------------------------
    def answer_question(self, case_id: int, session_id: int, question: str) -> Optional[Dict[str, Any]]:
        """
        Answer a question using retrieval-augmented generation from embeddings of case files.
        Returns a dict with 'answer' and 'source_chunks' (embedding ids) or None if no embeddings.
        """

        # 1) Embed the question
        embedding_response = openai.Embedding.create(
            model="text-embedding-3-small",
            input=question,
        )
        question_vector = embedding_response["data"][0]["embedding"]

        # 2) Fetch embeddings for the case
        embeddings = (
            self.db.query(models.embedding.Embedding)
            .join(models.case_file.CaseFile)
            .filter(models.case_file.CaseFile.case_id == case_id)
            .all()
        )

        if not embeddings:
            return None

        vectors = [e.vector for e in embeddings]
        similarities = self._cos_similarities(question_vector, vectors)

        TOP_K = 5
        top_indices = sorted(
            range(len(similarities)),
            key=lambda i: similarities[i],
            reverse=True,
        )[:TOP_K]

        rag_context = "\n\n".join(embeddings[i].chunk_text for i in top_indices)

        # 3) Fetch recent chat history - get last N messages, then reverse to chronological
        recent_msgs = (
            self.db.query(models.ChatMessage)
            .filter(models.ChatMessage.session_id == session_id)
            .order_by(models.ChatMessage.created_at.desc())
            .limit(6)
            .all()
        )
        recent_msgs = list(reversed(recent_msgs))

        # 4) Build ChatGPT messages array
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant. "
                    "Answer ONLY using the provided context. "
                    "If the answer is not in the context, say there is nothing related to this question in case files."
                ),
            }
        ]

        for msg in recent_msgs:
            # make sure role is valid (assistant/user/system)
            role = getattr(msg, "role", "user")
            content = getattr(msg, "content", "")
            messages.append({"role": role, "content": content})

        messages.append(
            {
                "role": "user",
                "content": f"Context:\n{rag_context}\n\nQuestion:\n{question}",
            }
        )

        # 5) Call ChatGPT
        completion = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=300,
            temperature=0,
        )

        answer_text = completion.choices[0].message.content.strip()

        # 6) Save assistant response
        try:
            self.db.add(
                models.ChatMessage(
                    session_id=session_id,
                    role="assistant",
                    content=answer_text,
                )
            )
            self.db.commit()
        except Exception as e:
            logger.exception("Failed to save assistant message: %s", e)
            # try rollback to keep session clean
            try:
                self.db.rollback()
            except Exception:
                pass

        return {
            "answer": answer_text,
            "source_chunks": [embeddings[i].id for i in top_indices],
        }

    # -------------------------
    # NEW: Case metadata extraction
    # -------------------------
    def extract_case_metadata_for_file(self, file_id: int) -> Dict[str, Any]:
        """
        Extracts structured case metadata from embeddings of a single file.
        Returns a dict (possibly empty) with the extracted fields.
        """
        embeddings = (
            self.db.query(models.embedding.Embedding)
            .filter(models.embedding.Embedding.file_id == file_id)
            .all()
        )

        if not embeddings:
            return {}

        # generic summary query to find informative chunks
        query = "case parties court judge lawyer filing date evidence next hearing deadline attorney"

        embedding_response = openai.Embedding.create(
            model="text-embedding-3-small",
            input=query,
        )
        query_vector = embedding_response["data"][0]["embedding"]

        vectors = [e.vector for e in embeddings]
        similarities = self._cos_similarities(query_vector, vectors)

        TOP_K = 8
        top_indices = sorted(
            range(len(similarities)),
            key=lambda i: similarities[i],
            reverse=True,
        )[:TOP_K]

        context = "\n\n".join(embeddings[i].chunk_text for i in top_indices)

        prompt = f"""
You are a legal AI assistant.

Extract the following fields from the document text and return ONLY valid JSON.

Fields:
- parties : string (e.g., "Plaintiff vs Defendant")
- court_name : string
- filing_date (YYYY-MM-DD or null) : date
- judge : string
- attorney : string
- next_court_date (YYYY-MM-DD or null) : date
- strong_evidence : string
- approaching_deadline (true/false): boolean
- case_description : string

If a field is missing, use null.

Document:
{context}
"""

        completion = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=700,
            temperature=0,
        )

        raw = completion.choices[0].message.content.strip()

        # Safe JSON extraction
        try:
            return json.loads(raw)
        except Exception:
            match = re.search(r"\{.*\}", raw, re.S)
            if not match:
                return {}
            try:
                return json.loads(match.group())
            except Exception:
                logger.exception("Failed to parse JSON from model output: %s", raw)
                return {}

    # -------------------------
    # Helper methods used in merging
    # -------------------------
    def _parse_date(self, value: Any) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value))
        except Exception:
            # try to extract yyyy-mm-dd via regex
            m = re.search(r"(\d{4}-\d{2}-\d{2})", str(value))
            if m:
                try:
                    return date.fromisoformat(m.group(1))
                except Exception:
                    return None
            return None

    def _merge_jsonb(self, existing: Any, new: Any) -> Any:
        """
        Merge JSONB parties field in a conservative way:
        - If existing is None -> return new
        - If both dicts -> fill missing keys in existing with new's non-empty values
        - If lists/scalars -> produce a merged list with unique elements where appropriate
        """
        if existing is None:
            return new
        if new is None:
            return existing

        if isinstance(existing, dict) and isinstance(new, dict):
            merged = dict(existing)
            for k, v in new.items():
                if merged.get(k) in (None, "", [], {} ) and v not in (None, "", [], {}):
                    merged[k] = v
            return merged

        if isinstance(existing, list):
            out = list(existing)
            if isinstance(new, list):
                for item in new:
                    if item not in out:
                        out.append(item)
            else:
                if new not in out:
                    out.append(new)
            return out

        if isinstance(existing, str):
            if isinstance(new, str):
                if existing.strip() == new.strip():
                    return existing
                return [existing, new] if new not in [existing] else existing
            if isinstance(new, list):
                out = [existing]
                for item in new:
                    if item not in out:
                        out.append(item)
                return out

        if existing != new:
            return [existing, new]
        return existing

    def _append_text_field(self, existing: Optional[str], new: Optional[str]) -> Optional[str]:
        """
        Append `new` to `existing` separated by two newlines, avoid exact duplicate text.
        If existing is None/empty and new exists, return new.
        """
        if not new or str(new).strip() == "":
            return existing
        new_s = str(new).strip()
        if not existing or str(existing).strip() == "":
            return new_s
        existing_s = str(existing).strip()
        # avoid exact duplicate or substring duplication
        if new_s in existing_s:
            return existing_s
        return existing_s + "\n\n" + new_s

    # -------------------------
    # Merge metadata into DB
    # -------------------------
    def merge_case_metadata_for_case(self, case_id: int, new_meta: Dict[str, Any]) -> Optional[Any]:


        if not new_meta:
            return None

        db = self.db

        def maybe_none(v: Any) -> Any:
            if v in (None, "null", "None", ""):
                return None
            return v

        nm = {k: maybe_none(v) for k, v in new_meta.items()}

        try:
            existing_meta = (
                db.query(models.case_metadata.CaseMetadata)
                .filter(models.case_metadata.CaseMetadata.case_id == case_id)
                .one_or_none()
            )



            # -------------------------
            # CREATE CASE
            # -------------------------
            if existing_meta is None:
                # print("🆕 No existing CaseMetadata, creating new row")

                cm = models.case_metadata.CaseMetadata(
                    case_id=case_id,
                    parties=nm.get("parties"),
                    court_name=nm.get("court_name"),
                    filing_date=self._parse_date(nm.get("filing_date")),
                    judge=nm.get("judge"),
                    attorney=nm.get("attorney"),
                    next_court_date=self._parse_date(nm.get("next_court_date")),
                    strong_evidence=nm.get("strong_evidence"),
                    approaching_deadline=(
                        True
                        if nm.get("approaching_deadline") in (True, "true", "True", "1", 1)
                        else False
                    )
                    if nm.get("approaching_deadline") is not None
                    else None,
                    case_description=nm.get("case_description"),
                )

                # print("🧾 Creating CaseMetadata with values:")
                # print("parties:", cm.parties)
                # print("court_name:", cm.court_name)
                # print("strong_evidence:", cm.strong_evidence)
                # print("case_description:", cm.case_description)

                db.add(cm)
                # print("💾 Committing new CaseMetadata...")
                db.commit()
                db.refresh(cm)

                # print("✅ CaseMetadata CREATED with id:", cm.id)
                # print("========== MERGE END ==========\n")
                return cm

            # -------------------------
            # UPDATE CASE
            # -------------------------
            # print("✏️ Updating existing CaseMetadata id:", existing_meta.id)

            # print("BEFORE UPDATE:")
            # print("strong_evidence:", existing_meta.strong_evidence)
            # print("case_description:", existing_meta.case_description)
            # print("approaching_deadline:", existing_meta.approaching_deadline)

            # PARTIES
            if getattr(existing_meta, "parties", None) in (None, "") and nm.get("parties") is not None:
                # print("✔ Filling empty parties")
                existing_meta.parties = nm.get("parties")
            elif nm.get("parties") is not None:
                # print("🔀 Merging parties")
                existing_meta.parties = self._merge_jsonb(existing_meta.parties, nm.get("parties"))

            # simple scalar fields
            for field in ("court_name", "judge", "attorney"):
                new_val = nm.get(field)
                if getattr(existing_meta, field, None) in (None, "") and new_val is not None:
                    # print(f"✔ Filling {field}: {new_val}")
                    setattr(existing_meta, field, new_val)

            # dates
            if getattr(existing_meta, "filing_date", None) is None and nm.get("filing_date") is not None:
                parsed = self._parse_date(nm.get("filing_date"))
                # print("Parsed filing_date:", parsed)
                if parsed:
                    existing_meta.filing_date = parsed

            if getattr(existing_meta, "next_court_date", None) is None and nm.get("next_court_date") is not None:
                parsed = self._parse_date(nm.get("next_court_date"))
                # print("Parsed next_court_date:", parsed)
                if parsed:
                    existing_meta.next_court_date = parsed

            # approaching_deadline
            if existing_meta.approaching_deadline is None and nm.get("approaching_deadline") is not None:
                new_deadline = nm.get("approaching_deadline") in (True, "true", "True", "1", 1)
                # print("✔ Setting approaching_deadline to:", new_deadline)
                existing_meta.approaching_deadline = new_deadline

            # append fields
            # print("🔗 Appending strong_evidence...")
            existing_meta.strong_evidence = self._append_text_field(
                existing_meta.strong_evidence,
                nm.get("strong_evidence"),
            )

            # print("🔗 Appending case_description...")
            existing_meta.case_description = self._append_text_field(
                existing_meta.case_description,
                nm.get("case_description"),
            )

            # print("AFTER UPDATE (before commit):")
            # print("strong_evidence:", existing_meta.strong_evidence)
            # print("case_description:", existing_meta.case_description)
            # print("approaching_deadline:", existing_meta.approaching_deadline)

            # print("💾 Committing updates...")
            db.add(existing_meta)
            db.commit()
            db.refresh(existing_meta)

            # print("✅ CaseMetadata UPDATED successfully")
            # print("========== MERGE END ==========\n")
            return existing_meta

        except Exception as e:
            # print("❌ EXCEPTION during merge:", e)
            try:
                db.rollback()
                # print("🔄 Rolled back transaction")
            except Exception:
                pass
          #  print("========== MERGE FAILED ==========\n")
            return None
