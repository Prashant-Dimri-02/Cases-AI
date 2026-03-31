# app/services/mom_service.py

from app.core.config import settings
import openai

openai.api_key = settings.OPENAI_API_KEY


class MOMService:
    def __init__(self, db):
        self.db = db

    def generate_mom(self, case_id: int, transcript: str):
        try:
            # 🔥 STEP 1: Clean transcript
            cleaned_transcript = self.clean_transcript(transcript)

            # 🔥 STEP 2: Generate MOM
            mom = self.create_mom(cleaned_transcript)

            return {
                "case_id": case_id,
                "answer": mom,   # 👈 IMPORTANT (so your C# stays SAME)
                "cleaned_transcript": cleaned_transcript
            }

        except Exception as e:
            print("MOM generation error:", str(e))
            return None

    # ✅ CLEAN TRANSCRIPT
    def clean_transcript(self, transcript: str) -> str:
        prompt = f"""
You are an expert legal assistant.

Clean the following meeting transcript:
- Remove noise, filler words, repetition
- Fix grammar
- Keep meaning intact
- Keep it professional
- DO NOT summarize

Transcript:
{transcript}
"""

        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",   # ✅ fast + cheap
            messages=[
                {"role": "system", "content": "You clean legal transcripts."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )

        return response["choices"][0]["message"]["content"].strip()

    # ✅ GENERATE MOM
    def create_mom(self, cleaned_transcript: str) -> str:
        prompt = f"""
You are a professional legal meeting assistant.

Convert the transcript into structured Minutes of Meeting (MOM).

Format STRICTLY:

1. Meeting Title
2. Date & Time
3. Participants
4. Agenda
5. Discussion Points
6. Decisions Made
7. Action Items
8. Next Steps

Keep it formal and structured.

Transcript:
{cleaned_transcript}
"""

        response = openai.ChatCompletion.create(
            model="gpt-4o",   # ✅ better quality for MOM
            messages=[
                {"role": "system", "content": "You generate professional MOM documents."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )

        return response["choices"][0]["message"]["content"].strip()