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
