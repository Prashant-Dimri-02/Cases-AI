# app/services/qa_service.py
import os
import tempfile
from typing import Any, Dict, Optional, List
from datetime import date, datetime
import json
import re
import logging
from app.core.azure_openai import client
from fastapi import UploadFile
from app.schemas import file
from app.schemas.qa import SpeechResponse
import numpy as np
from sqlalchemy.orm import Session
from app.services.embedding_service import EmbeddingService
from pydub import AudioSegment
import azure.cognitiveservices.speech as speechsdk
from app.core.config import settings
from app import models

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

    
    def _clean_question(self, text: str) -> str:
        """
        Extract the most meaningful question from a transcript.
        """

        if not text:
            return text

        # remove speaker labels
        text = re.sub(r"User\s*\d+\s*:", "", text, flags=re.I)

        # split sentences
        sentences = re.split(r"[.\n]", text)

        # keep meaningful sentences
        candidates = []
        for s in sentences:
            s = s.strip()
            if len(s) > 10:
                candidates.append(s)

        if not candidates:
            return text.strip()

        # prefer last meaningful sentence
        return candidates[-1]
    
    
    # -------------------------
    # Q/A with RAG
    # -------------------------
    def answer_question(
        self,
        case_id: int,
        question: str,
        session_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Answer a question using retrieval-augmented generation from embeddings of case files.
        Perfectly handles noisy speech + real ChatGPT-style casual conversation.
        """
        # ------------------------------------------------------------------
        # 1. Basic cleaning
        # ------------------------------------------------------------------
        question = self._clean_question(question).strip()
        if not question:
            return {"answer": "Sorry, I didn't catch that. Could you please repeat?", "source_chunks": []}

        # ------------------------------------------------------------------
        # 2. ADD TO KNOWLEDGE BASE (unchanged)
        # ------------------------------------------------------------------
        def _is_add_intent_and_extract(q: str) -> Optional[str]:
            pattern = re.compile(
                r'add\b.*?(?:knowledge\s*base|knowledge|db|database|kb)[\s\:\-]*\s*(.*)',
                flags=re.I | re.S
            )
            m = pattern.search(q)
            if m and m.group(1).strip():
                return m.group(1).strip()
            simple_pattern = re.compile(r'add(?: this)?\s*[:\-]\s*(.*)', flags=re.I | re.S)
            m2 = simple_pattern.search(q)
            if m2 and m2.group(1).strip():
                return m2.group(1).strip()
            return None

        add_content = _is_add_intent_and_extract(question)
        if add_content is not None:
            # [YOUR EXISTING ADD-TO-KB CODE – exactly the same as before]
            try:
                case_file = (
                    self.db.query(models.case_file.CaseFile)
                    .filter(models.case_file.CaseFile.case_id == case_id)
                    .order_by(models.case_file.CaseFile.id.asc())
                    .first()
                )
                if case_file is None:
                    return {
                        "answer": "No case file found for this case id. Cannot add to knowledge base.",
                        "source_chunks": [],
                    }
                embedding_row = (
                    self.db.query(models.embedding.Embedding)
                    .filter(models.embedding.Embedding.file_id == case_file.id)
                    .order_by(models.embedding.Embedding.id.asc())
                    .first()
                )
                embedding_service = EmbeddingService()
                if embedding_row is None:
                    new_chunk_text = add_content
                    new_vector = embedding_service.create_embedding(new_chunk_text)
                    new_embedding = models.embedding.Embedding(
                        file_id=case_file.id,
                        chunk_text=new_chunk_text,
                        vector=new_vector,
                    )
                    self.db.add(new_embedding)
                    self.db.commit()
                    return {
                        "answer": "Successfully added to knowledge base and created new embedding.",
                        "source_chunks": [new_embedding.id],
                    }
                combined_text = embedding_row.chunk_text + "\n\n" + add_content
                new_vector = embedding_service.create_embedding(combined_text)
                embedding_row.chunk_text = combined_text
                embedding_row.vector = new_vector
                self.db.add(embedding_row)
                self.db.commit()
                return {
                    "answer": "Successfully added to knowledge base and updated embedding.",
                    "source_chunks": [embedding_row.id],
                }
            except Exception as e:
                logger.exception("Failed to add content to knowledge base: %s", e)
                self.db.rollback()
                return {
                    "answer": f"Failed to add to knowledge base: {str(e)}",
                    "source_chunks": [],
                }

        # ------------------------------------------------------------------
        # 3. REFINE + STRICT greeting detection (this is the fix)
        # ------------------------------------------------------------------
        refine_prompt = f"""
    You are an expert at cleaning noisy Azure Speech-to-Text output.

    The text below is a **single noisy sentence** from a legal assistant bot.

    Tasks:
    1. Fix speech recognition errors (e.g. "loyen" → "", "lawyan" → "", "policy bot" → "").
    2. Remove fillers (um, uh, like, you know...).
    3. Make it clear and natural.
    4. Return **ONLY** one of the following (nothing else):

    • The exact word `GREETING` → **only** if the entire sentence is pure casual talk with **zero** legal or command intent.
    • Otherwise return the cleaned legal question.

    Examples where you **MUST** return `GREETING`:
    - "hello"
    - "hi"
    - "how are you"
    - "how are you doing"
    - "thanks"
    - "good morning"

    Examples where you **MUST NOT** return `GREETING` (return the cleaned question instead):
    - "hi what is the court date"
    - "hello show me the transcript"
    - "how are you doing with the case file"

    Noisy transcript: {question}
    """

        refine_response = client.chat.completions.create(
            model=settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
            messages=[{"role": "user", "content": refine_prompt}],
            temperature=0,
            max_tokens=120,
        )
        refined = refine_response.choices[0].message.content.strip()

        # === EXTRA SAFETY CHECK (prevents the exact bug you showed) ===
        intent_keywords = {
            "transcript", "testing", "bot", "qa", "case", "file", "court", "date",
            "document", "show me", "what is", "tell me", "question", "answer"
        }
        lower_original = question.lower()
        lower_refined = refined.lower()

        has_intent = any(kw in lower_original for kw in intent_keywords) or \
                    any(kw in lower_refined for kw in intent_keywords)

        if refined.upper() == "GREETING" and has_intent:
            refined = question  # force real question path

        if refined.upper() == "GREETING":
            greeting_response = client.chat.completions.create(
                model=settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a natural human assistant. "
                            "Respond to greetings in a casual, friendly, and varied way. "
                            "DO NOT repeat the same sentence every time. "
                            "Avoid generic templates like 'How can I help you today?' unless it fits naturally."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"User said: {question}"
                    }
                ],
                temperature=0.9,   # 🔥 IMPORTANT (increase randomness)
                max_tokens=50,
            )

            polite_reply = greeting_response.choices[0].message.content.strip()

            if session_id is not None:
                self.db.add(models.ChatMessage(
                    session_id=session_id,
                    role="assistant",
                    content=polite_reply
                ))
                self.db.commit()

            return {"answer": polite_reply, "source_chunks": []}
        # Use the refined (clean) question from now on
        question = refined

        # ------------------------------------------------------------------
        # 4. NORMAL RAG FLOW (unchanged)
        # ------------------------------------------------------------------
        embedding_response = client.embeddings.create(
            model=settings.AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
            input=question,
        )
        question_vector = embedding_response.data[0].embedding

        embeddings = (
            self.db.query(models.embedding.Embedding)
            .join(models.case_file.CaseFile)
            .filter(models.case_file.CaseFile.case_id == case_id)
            .all()
        )
        if not embeddings:
            return {"answer": "There are no case files for this case yet.", "source_chunks": []}

        vectors = [e.vector for e in embeddings]
        similarities = self._cos_similarities(question_vector, vectors)

        TOP_K = 4
        keywords = set(question.lower().split())
        scores = []
        for i, emb in enumerate(embeddings):
            sim = similarities[i]
            text = emb.chunk_text.lower()
            keyword_score = sum(1 for k in keywords if k in text)
            final_score = sim + (0.05 * keyword_score)
            scores.append((i, final_score))

        SIM_THRESHOLD = 0.20
        filtered = [(i, score) for i, score in scores if similarities[i] > SIM_THRESHOLD]
        if not filtered:
            return {
                "answer": "There is nothing related to this question in case files.",
                "source_chunks": [],
            }

        top_indices = [i for i, _ in sorted(filtered, key=lambda x: x[1], reverse=True)[:TOP_K]]
        candidate_chunks = [embeddings[i].chunk_text for i in top_indices]
        candidate_text = "\n\n".join(f"[{idx}] {text}" for idx, text in enumerate(candidate_chunks))

        rerank_prompt = f"""
    Which of the following document chunks best answers the question?
    Question: {question}

    Chunks:
    {candidate_text}

    Return the indices of the most relevant chunks as a JSON list like: [0,2,3]
    """
        rerank_response = client.chat.completions.create(
            model=settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
            messages=[{"role": "user", "content": rerank_prompt}],
            temperature=0,
        )
        reranked = rerank_response.choices[0].message.content.strip()
        try:
            rerank_indices = json.loads(reranked)
        except:
            rerank_indices = list(range(len(candidate_chunks)))

        rag_context = "\n\n".join(
            f"[SOURCE {idx+1}]\n{candidate_chunks[i]}"
            for idx, i in enumerate(rerank_indices[:4])
        )

        # Final answer
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful legal AI assistant.\n\n"
                    "Rules:\n"
                    "1. Answer ONLY using the provided context from case files.\n"
                    "2. If the context does not contain the answer, reply exactly: "
                    "'There is nothing related to this question in case files.'\n"
                    "3. Do NOT invent or assume any legal facts.\n"
                    "4. Summarize clearly and professionally."
                ),
            }
        ]

        if session_id is not None:
            recent_msgs = (
                self.db.query(models.ChatMessage)
                .filter(models.ChatMessage.session_id == session_id)
                .order_by(models.ChatMessage.created_at.desc())
                .limit(6)
                .all()
            )
            recent_msgs = list(reversed(recent_msgs))
            for msg in recent_msgs:
                messages.append({"role": getattr(msg, "role", "user"), "content": getattr(msg, "content", "")})

        messages.append(
            {
                "role": "user",
                "content": f"Context:\n{rag_context}\n\nQuestion:\n{question}",
            }
        )

        completion = client.chat.completions.create(
            model=settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
            messages=messages,
            max_tokens=300,
            temperature=0,
        )
        answer_text = completion.choices[0].message.content.strip()

        if session_id is not None:
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
                self.db.rollback()

        return {
            "answer": answer_text,
            "source_chunks": [
                embeddings[top_indices[i]].id for i in rerank_indices[:4]
            ],
        }
    
    # -------------------------
    # NEW: Case metadata extraction
    # -------------------------
    
    
    def _normalize_court_dates(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        If next_court_date < today:
            - move it to previous_court_date
            - set next_court_date = None
        """
        today = date.today()

        next_court_date = data.get("next_court_date")
        prev_court_date = data.get("previous_court_date")
        
        if next_court_date:
            try:
                next_dt = datetime.strptime(next_court_date, "%Y-%m-%d").date()

                if next_dt < today:
                    # Move to previous_court_date
                    data["previous_court_date"] = next_court_date
                    data["next_court_date"] = None

            except ValueError:
                # Invalid date format → ignore safely
                pass
        return data
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

        embedding_response = client.embeddings.create(
            model=settings.AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
            input=query,
        )
        query_vector = embedding_response.data[0].embedding
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
- previous_court_date : (YYYY-MM-DD or null) : date

If a field is missing, use null.

Document:
{context}
"""

        completion = client.chat.completions.create(
            model=settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=700,
            temperature=0,
        )

        raw = completion.choices[0].message.content.strip()
        # Safe JSON extraction
        try:
            data = json.loads(raw)
        except Exception:
            match = re.search(r"\{.*\}", raw, re.S)
            if not match:
                return {}
            try:
                data = json.loads(match.group())
            except Exception:
                logger.exception("Failed to parse JSON from model output: %s", raw)
                return {}

        # 🔹 Normalize court dates
        data = self._normalize_court_dates(data)

        return data



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
                cm = models.case_metadata.CaseMetadata(
                    case_id=case_id,
                    parties=nm.get("parties"),
                    court_name=nm.get("court_name"),
                    filing_date=self._parse_date(nm.get("filing_date")),
                    judge=nm.get("judge"),
                    attorney=nm.get("attorney"),
                    next_court_date=self._parse_date(nm.get("next_court_date")),
                    previous_court_date=self._parse_date(nm.get("previous_court_date")),
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

                db.add(cm)
                db.commit()
                db.refresh(cm)
                return cm

            # -------------------------
            # UPDATE CASE
            # -------------------------

            # PARTIES
            if getattr(existing_meta, "parties", None) in (None, "") and nm.get("parties") is not None:
                existing_meta.parties = nm.get("parties")
            elif nm.get("parties") is not None:
                existing_meta.parties = self._merge_jsonb(existing_meta.parties, nm.get("parties"))

            # simple scalar fields
            for field in ("court_name", "judge", "attorney"):
                new_val = nm.get(field)
                if getattr(existing_meta, field, None) in (None, "") and new_val is not None:
                    setattr(existing_meta, field, new_val)

            # -------------------------
            # DATES
            # -------------------------

            # filing_date (only fill if empty)
            if getattr(existing_meta, "filing_date", None) is None and nm.get("filing_date") is not None:
                parsed = self._parse_date(nm.get("filing_date"))
                if parsed:
                    existing_meta.filing_date = parsed

            # next_court_date merge logic
            new_next_raw = nm.get("next_court_date")
            if new_next_raw is not None:
                new_next = self._parse_date(new_next_raw)

                if new_next:
                    existing_next = getattr(existing_meta, "next_court_date", None)

                    # Case 1: no existing next_court_date → just set it
                    if existing_next is None:
                        existing_meta.next_court_date = new_next

                    # Case 2: new date is greater → shift old to previous, update next
                    elif new_next > existing_next:
                        existing_meta.previous_court_date = existing_next
                        existing_meta.next_court_date = new_next

                    # else: ignore (older or same date)

            # -------------------------
            # approaching_deadline
            # -------------------------
            if existing_meta.approaching_deadline is None and nm.get("approaching_deadline") is not None:
                new_deadline = nm.get("approaching_deadline") in (True, "true", "True", "1", 1)
                existing_meta.approaching_deadline = new_deadline

            # -------------------------
            # append fields
            # -------------------------
            existing_meta.strong_evidence = self._append_text_field(
                existing_meta.strong_evidence,
                nm.get("strong_evidence"),
            )

            existing_meta.case_description = self._append_text_field(
                existing_meta.case_description,
                nm.get("case_description"),
            )

            db.add(existing_meta)
            db.commit()
            db.refresh(existing_meta)
            return existing_meta

        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            return None

    async def process_audio_file(self, file: UploadFile) -> SpeechResponse:
        # 1️⃣ Load env safely
        AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
        AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION")

        if not AZURE_SPEECH_KEY or not AZURE_SPEECH_REGION:
            raise RuntimeError("Azure Speech env vars not set")

        # 2️⃣ Preserve real file extension
        suffix = os.path.splitext(file.filename)[1] or ".webm"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            data = await file.read()
            tmp.write(data)
            input_path = tmp.name

        # 3️⃣ Convert to WAV
        try:
            audio = AudioSegment.from_file(input_path)
            audio = audio.set_channels(1).set_frame_rate(16000)

            wav_path = input_path + ".wav"
            audio.export(wav_path, format="wav")

        except Exception as e:
            raise RuntimeError("Audio conversion failed")

        # 4️⃣ Azure Speech
        try:
            speech_config = speechsdk.SpeechConfig(
                subscription=AZURE_SPEECH_KEY,
                region=AZURE_SPEECH_REGION
            )
            speech_config.speech_recognition_language = "en-IN"

            audio_config = speechsdk.AudioConfig(filename=wav_path)
            recognizer = speechsdk.SpeechRecognizer(
                speech_config=speech_config,
                audio_config=audio_config
            )

            result = recognizer.recognize_once()

        except Exception as e:
            raise RuntimeError("Azure Speech failed")

        # 5️⃣ Cleanup
        try:
            os.remove(input_path)
            os.remove(wav_path)
        except Exception as e:
            print("Cleanup failed:", e)

        # 6️⃣ Return normalized response
        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            return SpeechResponse(
                text=result.text,
                confidence=None,
                language="en-IN",
                duration_ms=None,
                provider="azure"
            )

        elif result.reason == speechsdk.ResultReason.NoMatch:
            return SpeechResponse(
                text="",
                confidence=None,
                language="en-IN",
                duration_ms=None,
                provider="azure"
            )

        else:
            return SpeechResponse(
                text=f"Error: {result.reason}",
                confidence=None,
                language="en-IN",
                duration_ms=None,
                provider="azure"
            )





