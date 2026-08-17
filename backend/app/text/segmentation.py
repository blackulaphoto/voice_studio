from __future__ import annotations

import re

PROTECTED = ("Mr.", "Mrs.", "Ms.", "Dr.", "Prof.", "Sr.", "Jr.", "U.S.", "U.K.", "e.g.", "i.e.")


def segment_text(text: str, max_chars: int = 420) -> list[str]:
    """Split long text at paragraph/sentence/clause boundaries while protecting abbreviations."""
    clean = re.sub(r"[ \t]+", " ", text.strip())
    if not clean:
        return []
    protected = clean
    tokens: dict[str, str] = {}
    for index, phrase in enumerate(PROTECTED):
        token = f"<ABBR{index}>"
        tokens[token] = phrase
        protected = protected.replace(phrase, token)
    protected = re.sub(r"(?<=\d)\.(?=\d)", "<DECIMAL>", protected)
    units = re.split(r"(?<=[.!?])\s+|\n{2,}", protected)
    restored = []
    for unit in units:
        unit = unit.replace("<DECIMAL>", ".")
        for token, phrase in tokens.items():
            unit = unit.replace(token, phrase)
        if unit.strip():
            restored.append(unit.strip())

    chunks: list[str] = []
    current = ""
    for unit in restored:
        if len(unit) > max_chars:
            clauses = re.split(r"(?<=[,;:])\s+", unit)
        else:
            clauses = [unit]
        for clause in clauses:
            candidate = f"{current} {clause}".strip()
            if current and len(candidate) > max_chars:
                chunks.append(current)
                current = clause
            else:
                current = candidate
    if current:
        chunks.append(current)
    return chunks


# Pre-pace, "at rest" pause weights in seconds for what follows each boundary punctuation mark.
# These are later scaled by the pause_scale delivery dial and then by the overall pace/speed
# tempo change along with everything else — see concatenate_with_pauses in audio/processing.py
# and its caller in main.py's synthesize().
_SENTENCE_PAUSE = 0.38
_CLAUSE_PAUSE = 0.28
_COMMA_PAUSE = 0.18
_ELLIPSIS_PAUSE = 0.32
_PAUSE_WEIGHTS = {".": _SENTENCE_PAUSE, "!": _SENTENCE_PAUSE, "?": _SENTENCE_PAUSE,
                  ";": _CLAUSE_PAUSE, ":": _CLAUSE_PAUSE, "—": _CLAUSE_PAUSE, ",": _COMMA_PAUSE}
_BOUNDARY = re.compile(r"(\.\.\.|[.!?;:—,])\s+")


def _merge_short_segments(segments: list[tuple[str, float]], min_words: int = 3) -> list[tuple[str, float]]:
    """Fold fragments shorter than min_words into the following segment.

    A lone "Brandon," synthesized on its own tends to come out with clipped, unnatural
    intonation (TTS models generally need a little more context for natural prosody), and each
    extra fragment is another full model call. The pause that would have followed the short
    fragment is dropped — the two pieces become one continuous synthesis unit.
    """
    if len(segments) <= 1:
        return segments
    merged: list[tuple[str, float]] = []
    buffer_text = ""
    for text, pause in segments:
        buffer_text = f"{buffer_text} {text}".strip() if buffer_text else text
        if len(buffer_text.split()) >= min_words:
            merged.append((buffer_text, pause))
            buffer_text = ""
    if buffer_text:
        if merged:
            prev_text, prev_pause = merged[-1]
            merged[-1] = (f"{prev_text} {buffer_text}".strip(), prev_pause)
        else:
            merged.append((buffer_text, 0.0))
    return merged


def _cap_segment_count(segments: list[tuple[str, float]], max_segments: int) -> list[tuple[str, float]]:
    """Merge adjacent segments until the count is at or below max_segments.

    Each phrase segment costs one full, separate CPU inference call — a long paragraph naively
    segmented at every comma/period can produce a dozen-plus segments, turning what used to be
    one generation into a dozen-plus sequential ones (discovered 2026-08-16/17: a long input
    took 10+ minutes because of this, real but not a hang). Repeatedly merges the pair joined by
    the *smallest* pause weight first — the least perceptually costly boundary to lose — so
    long-form text degrades toward coarser pausing rather than losing sentence-level pauses
    first. This is a stopgap, not a real long-form solution; see segment_text and the roadmap's
    "long-form stability and intelligent segmentation" item for the eventual real fix.
    """
    segments = list(segments)
    while len(segments) > max_segments:
        merge_index = min(range(len(segments) - 1), key=lambda i: segments[i][1])
        (text_a, _pause_a), (text_b, pause_b) = segments[merge_index], segments[merge_index + 1]
        segments[merge_index:merge_index + 2] = [(f"{text_a} {text_b}".strip(), pause_b)]
    return segments


def segment_phrases(text: str, max_segments: int = 8) -> list[tuple[str, float]]:
    """Split text into natural phrase segments, each paired with the pause after it.

    Unlike segment_text (long-form ~420-char chunking for a different purpose), this splits at
    every sentence ending and every clause boundary (comma/semicolon/colon/em-dash/ellipsis) so
    each phrase can be synthesized separately and reassembled with a guaranteed, controllable
    pause at that boundary — the model's own raw generation cannot be relied on to leave a gap
    there at all. Protects abbreviations/decimals the same way segment_text does. The last
    segment always carries pause_after=0.0; the true end of the audio is trim_outer_silence's job,
    not an inserted gap. Capped at max_segments (see _cap_segment_count) so long text can't turn
    into dozens of sequential model calls.
    """
    clean = re.sub(r"[ \t]+", " ", text.strip())
    if not clean:
        return []
    protected = clean
    tokens: dict[str, str] = {}
    for index, phrase in enumerate(PROTECTED):
        token = f"<ABBR{index}>"
        tokens[token] = phrase
        protected = protected.replace(phrase, token)
    protected = re.sub(r"(?<=\d)\.(?=\d)", "<DECIMAL>", protected)

    segments: list[tuple[str, float]] = []
    cursor = 0
    for match in _BOUNDARY.finditer(protected):
        piece = protected[cursor:match.start() + len(match.group(1))].strip()
        punct = match.group(1)
        pause = _ELLIPSIS_PAUSE if punct == "..." else _PAUSE_WEIGHTS.get(punct[-1], _COMMA_PAUSE)
        if piece:
            segments.append((piece, pause))
        cursor = match.end()
    tail = protected[cursor:].strip()
    if tail:
        segments.append((tail, 0.0))
    elif segments:
        last_text, _ = segments[-1]
        segments[-1] = (last_text, 0.0)

    restored: list[tuple[str, float]] = []
    for piece, pause in segments:
        for token, phrase in tokens.items():
            piece = piece.replace(token, phrase)
        piece = piece.replace("<DECIMAL>", ".")
        restored.append((piece, pause))
    return _cap_segment_count(_merge_short_segments(restored), max_segments)
