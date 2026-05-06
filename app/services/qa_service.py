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
    def _get_chat_history(self, session_id: int):
        recent_msgs = (
            self.db.query(models.ChatMessage)
            .filter(models.ChatMessage.session_id == session_id)
            .order_by(models.ChatMessage.created_at.asc())
            .all()
        )

        history = []

        for msg in recent_msgs:
            history.append({
                "role": msg.role,
                "content": msg.content
            })

        return history
    
    def _generate_rag_answer(
        self,
        case_id: int,
        question: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ):
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
            return {
                "answer": "There are no case files for this case yet.",
                "source_chunks": []
            }

        vectors = [e.vector for e in embeddings]
        similarities = self._cos_similarities(question_vector, vectors)

        TOP_K = 4
        keywords = set(question.lower().split())

        scores = []

        for i, emb in enumerate(embeddings):
            sim = similarities[i]
            text = emb.chunk_text.lower()

            keyword_score = sum(
                1 for k in keywords if k in text
            )

            final_score = sim + (0.05 * keyword_score)

            scores.append((i, final_score))

        SIM_THRESHOLD = 0.20

        filtered = [
            (i, score)
            for i, score in scores
            if similarities[i] > SIM_THRESHOLD
        ]

        if not filtered:
            return {
                "answer": "There is nothing related to this question in case files.",
                "source_chunks": []
            }

        top_indices = [
            i for i, _ in sorted(
                filtered,
                key=lambda x: x[1],
                reverse=True
            )[:TOP_K]
        ]

        candidate_chunks = [
            embeddings[i].chunk_text
            for i in top_indices
        ]

        rag_context = "\n\n".join(
            f"[SOURCE {idx+1}]\n{chunk}"
            for idx, chunk in enumerate(candidate_chunks)
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful legal AI assistant.\n"
                    "Use previous conversation history for conversational questions.\n"
                    "Use case file context for legal/case-specific questions.\n"
                    "If user asks about earlier conversation, use chat history.\n"
                    "If user asks about case facts, use case context.\n"
                    "Do not invent facts."
                )
            }
        ]

        if conversation_history:
            messages.extend(conversation_history)

        messages.append({
            "role": "system",
            "content": f"Case file context:\n{rag_context}"
        })

        messages.append({
            "role": "user",
            "content": question
        })

        completion = client.chat.completions.create(
            model=settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
            messages=messages,
            max_tokens=300,
            temperature=0,
        )

        answer_text = completion.choices[0].message.content.strip()

        return {
            "answer": answer_text,
            "source_chunks": [
                embeddings[i].id for i in top_indices
            ]
        }
        
    def answer_chat_question(
        self,
        case_id: int,
        question: str,
        session_id: int
    ):
        # ----------------------------------------
        # 1. Clean question
        # ----------------------------------------
        question = self._clean_question(question).strip()

        if not question:
            return {
                "answer": "Sorry, I didn't catch that.",
                "source_chunks": []
            }

        # ----------------------------------------
        # 2. Get previous chat history
        # ----------------------------------------
        history = self._get_chat_history(session_id)

        # ----------------------------------------
        # 3. Intent classification
        # ----------------------------------------
        classify_prompt = f"""
    You are classifying chat intent.

    Return ONLY one of these exact words:

    GREETING
    MEMORY
    FOLLOW_UP
    QUESTION

    Rules:

    GREETING:
    - hello
    - hi
    - good morning
    - how are you

    MEMORY:
    User asks about previous conversation/history.
    Examples:
    - what was my previous message
    - what did i ask before
    - what was my first question
    - what did you tell me

    FOLLOW_UP:
    User refers to previous answer/context.
    Examples:
    - explain this
    - tell this in short
    - make it shorter
    - simplify this
    - can you explain that
    - what do you mean
    - summarize it shortly
    - tell me briefly

    QUESTION:
    Standalone case/legal question.

    Message:
    {question}
    """

        classify_response = client.chat.completions.create(
            model=settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
            messages=[
                {
                    "role": "user",
                    "content": classify_prompt
                }
            ],
            temperature=0,
            max_tokens=20
        )

        intent = classify_response.choices[0].message.content.strip().upper()

        # fallback safety
        valid_intents = {
            "GREETING",
            "MEMORY",
            "FOLLOW_UP",
            "QUESTION"
        }

        if intent not in valid_intents:
            intent = "QUESTION"

        # ----------------------------------------
        # 4. GREETING handling
        # ----------------------------------------
        if intent == "GREETING":
            greeting_response = client.chat.completions.create(
                model=settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Reply naturally and conversationally to greetings. "
                            "Be friendly and human-like."
                        )
                    },
                    {
                        "role": "user",
                        "content": question
                    }
                ],
                temperature=0.8,
                max_tokens=50
            )

            answer = greeting_response.choices[0].message.content.strip()

            self.db.add(
                models.ChatMessage(
                    session_id=session_id,
                    role="assistant",
                    content=answer
                )
            )
            self.db.commit()

            return {
                "answer": answer,
                "source_chunks": []
            }

        # ----------------------------------------
        # 5. MEMORY handling
        # ----------------------------------------
        if intent == "MEMORY":
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Answer ONLY using previous conversation history. "
                        "Use earlier chat messages carefully."
                    )
                }
            ]

            messages.extend(history)

            messages.append({
                "role": "user",
                "content": question
            })

            completion = client.chat.completions.create(
                model=settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
                messages=messages,
                temperature=0,
                max_tokens=200
            )

            answer = completion.choices[0].message.content.strip()

            self.db.add(
                models.ChatMessage(
                    session_id=session_id,
                    role="assistant",
                    content=answer
                )
            )
            self.db.commit()

            return {
                "answer": answer,
                "source_chunks": []
            }

        # ----------------------------------------
        # 6. FOLLOW-UP handling
        # ----------------------------------------
        if intent == "FOLLOW_UP":
            messages = [
                {
                    "role": "system",
                    "content": (
                        "The user is referring to previous conversation context. "
                        "Use previous messages to resolve references like "
                        "'this', 'that', 'it'."
                    )
                }
            ]

            messages.extend(history)

            messages.append({
                "role": "user",
                "content": question
            })

            completion = client.chat.completions.create(
                model=settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
                messages=messages,
                temperature=0,
                max_tokens=200
            )

            answer = completion.choices[0].message.content.strip()

            self.db.add(
                models.ChatMessage(
                    session_id=session_id,
                    role="assistant",
                    content=answer
                )
            )
            self.db.commit()

            return {
                "answer": answer,
                "source_chunks": []
            }

        # ----------------------------------------
        # 7. Normal RAG question
        # ----------------------------------------
        result = self._generate_rag_answer(
            case_id=case_id,
            question=question,
            conversation_history=history
        )

        # ----------------------------------------
        # 8. Save assistant answer
        # ----------------------------------------
        try:
            self.db.add(
                models.ChatMessage(
                    session_id=session_id,
                    role="assistant",
                    content=result["answer"]
                )
            )
            self.db.commit()
        except Exception:
            self.db.rollback()

        return result
    
    def answer_voice_question(
        self,
        case_id: int,
        question: str
    ):
        # ----------------------------------------
        # 1. Clean raw speech text
        # ----------------------------------------
        question = self._clean_question(question).strip()

        if not question:
            return {
                "answer": "Sorry, I didn't catch that. Could you repeat?",
                "source_chunks": []
            }

        # ----------------------------------------
        # 2. Refine + classify intent
        # ----------------------------------------
        refine_prompt = f"""
    You are an AI assistant that processes speech-to-text input.

    Your tasks:
    1. Fix speech recognition mistakes
    2. Remove filler words
    3. Keep the original meaning
    4. Detect whether the user is:
    - GREETING
    - GENERAL_CHAT
    - CASE_QUERY

    Rules:
    - GREETING:
    hello, hi, good morning, hey, thank you, bye, how are you

    - GENERAL_CHAT:
    questions not related to case files
    casual conversation
    generic AI questions

    - CASE_QUERY:
    questions asking about the uploaded case/documents/context

    Return ONLY valid JSON.

    Format:
    {{
        "intent": "GREETING | GENERAL_CHAT | CASE_QUERY",
        "refined_question": "cleaned question"
    }}

    Input:
    {question}
    """

        refine_response = client.chat.completions.create(
            model=settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a speech-to-text refinement and "
                        "intent classification engine."
                    )
                },
                {
                    "role": "user",
                    "content": refine_prompt
                }
            ],
            temperature=0,
            max_tokens=150,
            response_format={"type": "json_object"}
        )

        import json

        try:
            parsed = json.loads(
                refine_response.choices[0].message.content
            )

            intent = parsed.get("intent", "").strip().upper()
            refined_question = (
                parsed.get("refined_question", question).strip()
            )

        except Exception:
            intent = "CASE_QUERY"
            refined_question = question

        # ----------------------------------------
        # 3. Greeting handling
        # ----------------------------------------
        if intent == "GREETING":

            greeting_response = client.chat.completions.create(
                model=settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
                messages=[
                    {
                        "role": "system",
                        "content": """
    You are a professional AI voice assistant.

    Rules:
    - Keep responses short
    - Natural conversational tone
    - Voice friendly
    - Do not give long explanations
    """
                    },
                    {
                        "role": "user",
                        "content": refined_question
                    }
                ],
                temperature=0.5,
                max_tokens=60
            )

            return {
                "answer": (
                    greeting_response
                    .choices[0]
                    .message
                    .content
                    .strip()
                ),
                "source_chunks": []
            }

        # ----------------------------------------
        # 4. General chat handling
        # ----------------------------------------
        if intent == "GENERAL_CHAT":

            general_response = client.chat.completions.create(
                model=settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
                messages=[
                    {
                        "role": "system",
                        "content": """
    You are a helpful AI voice assistant.

    Rules:
    - Keep answers concise
    - Voice friendly
    - Natural conversational style
    - Avoid very long answers
    """
                    },
                    {
                        "role": "user",
                        "content": refined_question
                    }
                ],
                temperature=0.5,
                max_tokens=120
            )

            return {
                "answer": (
                    general_response
                    .choices[0]
                    .message
                    .content
                    .strip()
                ),
                "source_chunks": []
            }

        # ----------------------------------------
        # 5. Case-specific RAG answer
        # ----------------------------------------
        return self._generate_rag_answer(
            case_id=case_id,
            question=refined_question
        )

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





