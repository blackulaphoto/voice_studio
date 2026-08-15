from app.text.normalization import normalize_text
from app.text.segmentation import segment_text


def test_currency_date_time_percent_and_decimal() -> None:
    spoken = normalize_text("Pay $149.95 on 2026-08-23 at 10:05 a.m. A 3.14% fee applies.")
    assert "one hundred forty-nine dollars and ninety-five cents" in spoken
    assert "August twenty-third" in spoken
    assert "ten oh five am" in spoken
    assert "three point one four percent" in spoken


def test_pronunciation_dictionary_is_phrase_aware() -> None:
    assert normalize_text("Nguyen called.", {"Nguyen": "nwin"}) == "nwin called."


def test_segmentation_protects_abbreviations_decimals_and_time() -> None:
    chunks = segment_text("Dr. Rivera measured 3.14 units at 10:30. It worked! " * 20, max_chars=120)
    assert len(chunks) > 1
    assert all(len(chunk) <= 150 for chunk in chunks)
    assert chunks[0].startswith("Dr. Rivera")
    assert "3.14" in chunks[0]
