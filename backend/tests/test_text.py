from app.text.normalization import normalize_text
from app.text.segmentation import segment_phrases, segment_text


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


def test_segment_phrases_splits_at_clause_and_sentence_boundaries() -> None:
    segments = segment_phrases(
        "Brandon, come here for a second — I need to tell you something, "
        "and I need you to really listen this time. Can you do that for me? "
        "Because this... this actually matters."
    )
    joined = " ".join(text for text, _ in segments)
    assert "Brandon" in joined and "matters" in joined
    # More than one segment: the whole point is that a single generate_voice_clone call is no
    # longer trusted to leave a gap at every comma/period on its own.
    assert len(segments) > 1
    # Sentence-ending punctuation must carry a longer pause than a mid-clause comma.
    sentence_pauses = [pause for text, pause in segments if text.rstrip().endswith((".", "!", "?"))]
    comma_pauses = [pause for text, pause in segments if text.rstrip().endswith(",")]
    assert sentence_pauses and all(p >= 0.3 for p in sentence_pauses[:-1] or [0.38])
    if comma_pauses:
        assert max(comma_pauses) < min(p for p in sentence_pauses if p > 0)
    # The last segment never carries a trailing pause — that's trim_outer_silence's job.
    assert segments[-1][1] == 0.0


def test_segment_phrases_protects_abbreviations_and_decimals() -> None:
    segments = segment_phrases("Dr. Rivera paid $3.14 for it. It worked great, honestly speaking today.")
    joined = " ".join(text for text, _ in segments)
    assert "Dr. Rivera" in joined
    assert "3.14" in joined


def test_segment_phrases_merges_short_fragments() -> None:
    # "Brandon," alone (one word) must not become its own standalone synthesis segment — it
    # should fold into the following clause rather than triggering an extra, awkward model call.
    segments = segment_phrases("Brandon, come here for a second, please listen carefully now.")
    assert all(len(text.split()) >= 3 for text, _ in segments)


def test_segment_phrases_handles_plain_text_and_empty_string() -> None:
    assert segment_phrases("") == []
    plain = segment_phrases("just one plain sentence with no punctuation at all")
    assert len(plain) == 1
    assert plain[0][1] == 0.0


def test_segment_phrases_caps_segment_count_on_long_text() -> None:
    # A long, comma/period-heavy paragraph must not turn into dozens of sequential model calls
    # (regression for a real incident: an uncapped long input took 10+ minutes because of this).
    long_text = "This is sentence number one, with a clause. " * 20
    segments = segment_phrases(long_text, max_segments=8)
    assert len(segments) <= 8
    # Capping must not drop any words — merging joins text, it never discards it.
    joined_word_count = sum(len(text.split()) for text, _ in segments)
    assert joined_word_count == len(long_text.split())


def test_segment_phrases_respects_custom_max_segments() -> None:
    long_text = "Alpha, beta, gamma, delta, epsilon, zeta, eta, theta, iota, kappa."
    assert len(segment_phrases(long_text, max_segments=3)) <= 3
