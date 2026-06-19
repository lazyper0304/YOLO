"""Text chunking service — splits text into overlapping chunks."""

from app.config import settings


def split_text(
    text: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[dict]:
    """Split text into chunks with overlap.

    Returns a list of dicts: {content: str, token_count: int, metadata: dict}
    """
    chunk_size = chunk_size or settings.RAG_CHUNK_SIZE
    chunk_overlap = chunk_overlap or settings.RAG_CHUNK_OVERLAP

    try:
        import tiktoken
        encoder = tiktoken.get_encoding("cl100k_base")
    except Exception:
        encoder = None

    def count_tokens(t: str) -> int:
        if encoder:
            return len(encoder.encode(t))
        return len(t) // 4  # rough estimate

    # Split by paragraphs first
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks = []
    current_text = ""
    current_tokens = 0
    char_offset = 0

    for para in paragraphs:
        para_tokens = count_tokens(para)

        # If single paragraph exceeds chunk_size, split by sentences
        if para_tokens > chunk_size:
            # Flush current buffer
            if current_text:
                chunks.append({
                    "content": current_text,
                    "token_count": current_tokens,
                    "metadata": {"char_offset": char_offset},
                })
                char_offset += len(current_text)
                current_text = ""
                current_tokens = 0

            # Split long paragraph by sentences
            sentences = _split_sentences(para)
            for sent in sentences:
                sent_tokens = count_tokens(sent)
                if current_tokens + sent_tokens > chunk_size and current_text:
                    chunks.append({
                        "content": current_text,
                        "token_count": current_tokens,
                        "metadata": {"char_offset": char_offset},
                    })
                    char_offset += len(current_text)
                    # Keep overlap
                    overlap_text = _get_tail(current_text, chunk_overlap, encoder)
                    current_text = overlap_text + sent
                    current_tokens = count_tokens(current_text)
                else:
                    current_text += (" " if current_text else "") + sent
                    current_tokens += sent_tokens
        else:
            # Normal paragraph
            if current_tokens + para_tokens > chunk_size and current_text:
                chunks.append({
                    "content": current_text,
                    "token_count": current_tokens,
                    "metadata": {"char_offset": char_offset},
                })
                char_offset += len(current_text)
                # Keep overlap
                overlap_text = _get_tail(current_text, chunk_overlap, encoder)
                current_text = overlap_text + "\n\n" + para if overlap_text else para
                current_tokens = count_tokens(current_text)
            else:
                current_text += ("\n\n" if current_text else "") + para
                current_tokens += para_tokens

    # Flush remaining
    if current_text.strip():
        chunks.append({
            "content": current_text,
            "token_count": current_tokens,
            "metadata": {"char_offset": char_offset},
        })

    return chunks


def _split_sentences(text: str) -> list[str]:
    """Split text by sentence-ending punctuation (Chinese + English)."""
    import re
    # Split on Chinese/English sentence endings, keep the delimiter
    parts = re.split(r'(?<=[。！？.!?])\s*', text)
    return [p.strip() for p in parts if p.strip()]


def _get_tail(text: str, max_tokens: int, encoder) -> str:
    """Get the last ~max_tokens worth of text for overlap."""
    if not text:
        return ""
    if encoder:
        tokens = encoder.encode(text)
        if len(tokens) <= max_tokens:
            return text
        tail_tokens = tokens[-max_tokens:]
        return encoder.decode(tail_tokens)
    # Fallback: approximate by characters
    char_count = max_tokens * 4
    if len(text) <= char_count:
        return text
    return text[-char_count:]
