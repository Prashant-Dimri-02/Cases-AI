# app/utils/text_chunker.py
def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100):
    tokens = text.split()
    chunks = []
    i = 0
    while i < len(tokens):
        chunk = tokens[i:i+chunk_size]
        chunks.append(" ".join(chunk))
        i += chunk_size - overlap
    return chunks
