from __future__ import annotations

import re
from datetime import datetime


ONES = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
        "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen")
TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
MONTHS = ("", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
ORDINALS = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth", 11: "eleventh", 12: "twelfth", 13: "thirteenth", 20: "twentieth", 21: "twenty-first", 22: "twenty-second", 23: "twenty-third", 24: "twenty-fourth", 25: "twenty-fifth", 26: "twenty-sixth", 27: "twenty-seventh", 28: "twenty-eighth", 29: "twenty-ninth", 30: "thirtieth", 31: "thirty-first"}


def number_words(value: int) -> str:
    if value < 0:
        return f"minus {number_words(-value)}"
    if value < 20:
        return ONES[value]
    if value < 100:
        return TENS[value // 10] + (f"-{ONES[value % 10]}" if value % 10 else "")
    if value < 1000:
        return f"{ONES[value // 100]} hundred" + (f" {number_words(value % 100)}" if value % 100 else "")
    for scale, label in ((1_000_000_000, "billion"), (1_000_000, "million"), (1000, "thousand")):
        if value >= scale:
            return f"{number_words(value // scale)} {label}" + (f" {number_words(value % scale)}" if value % scale else "")
    return str(value)


def normalize_text(text: str, pronunciations: dict[str, str] | None = None) -> str:
    """Normalize common English written forms without changing the saved original text."""
    output = text
    if pronunciations:
        for phrase in sorted(pronunciations, key=len, reverse=True):
            output = re.sub(rf"(?<!\w){re.escape(phrase)}(?!\w)", pronunciations[phrase], output, flags=re.IGNORECASE)

    def currency(match: re.Match[str]) -> str:
        dollars = int(match.group(1).replace(",", ""))
        cents = int((match.group(2) or "0").ljust(2, "0")[:2])
        value = f"{number_words(dollars)} dollar{'s' if dollars != 1 else ''}"
        return value + (f" and {number_words(cents)} cent{'s' if cents != 1 else ''}" if cents else "")

    def iso_date(match: re.Match[str]) -> str:
        try:
            date = datetime.strptime(match.group(0), "%Y-%m-%d")
            return f"{MONTHS[date.month]} {ORDINALS[date.day]}, {number_words(date.year)}"
        except ValueError:
            return match.group(0)

    def clock(match: re.Match[str]) -> str:
        hour, minute = int(match.group(1)), int(match.group(2))
        suffix = (match.group(3) or "").lower().replace(".", "")
        spoken = number_words(hour) + (" o'clock" if minute == 0 else f" {number_words(minute) if minute >= 10 else 'oh ' + number_words(minute)}")
        return f"{spoken} {suffix}".strip()

    output = re.sub(r"\$(\d[\d,]*)(?:\.(\d{1,2}))?", currency, output)
    output = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", iso_date, output)
    output = re.sub(r"\b(\d{1,2}):(\d{2})\s*([ap]\.?m\.?)?\b", clock, output, flags=re.IGNORECASE)
    output = re.sub(r"\b(\d+(?:\.\d+)?)%", lambda m: f"{decimal_words(m.group(1))} percent", output)
    output = re.sub(r"\b\d+\.\d+\b", lambda m: decimal_words(m.group(0)), output)
    output = re.sub(r"\b\d+\b", lambda m: number_words(int(m.group(0))), output)
    return re.sub(r"[ \t]+", " ", output).strip()


def decimal_words(value: str) -> str:
    whole, _, fraction = value.partition(".")
    return number_words(int(whole)) + (" point " + " ".join(ONES[int(d)] for d in fraction) if fraction else "")
