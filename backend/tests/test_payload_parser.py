"""Tests for the streaming payload extractor.

The interesting cases are all about chunk boundaries: the transport splits text
at arbitrary points, so a fence can arrive one character at a time. The
character-by-character test is the strongest guarantee here -- if the parser
survives that, no realistic chunking will break it.
"""

import json

import pytest

from app.payload_parser import PayloadStreamParser, strip_payloads

PAYLOAD = {"tool": "calculate_mortgage", "summary": {"monthly_payment": 3102.51},
           "charts": [{"id": "mortgage-balance", "data": []}]}
BLOCK = "```ic-payload\n" + json.dumps(PAYLOAD) + "\n```"


def collect(chunks):
    """Feed chunks and return (joined_text, [payload_events])."""
    parser = PayloadStreamParser()
    text, payloads = [], []
    for chunk in chunks:
        for event in parser.feed(chunk):
            (text if event["type"] == "text" else payloads).append(
                event["text"] if event["type"] == "text" else event)
    for event in parser.flush():
        (text if event["type"] == "text" else payloads).append(
            event["text"] if event["type"] == "text" else event)
    return "".join(text), payloads


def test_plain_text_passes_through_untouched():
    text, payloads = collect(["Hello ", "world."])
    assert text == "Hello world."
    assert payloads == []


def test_single_payload_in_one_chunk():
    text, payloads = collect([f"Before {BLOCK} after"])
    assert text == "Before  after"
    assert len(payloads) == 1
    assert payloads[0]["name"] == "calculate_mortgage"
    assert payloads[0]["payload"]["summary"]["monthly_payment"] == 3102.51


def test_payload_split_across_chunks():
    mid = len(BLOCK) // 2
    text, payloads = collect(["Before ", BLOCK[:mid], BLOCK[mid:], " after"])
    assert text == "Before  after"
    assert len(payloads) == 1


def test_opening_fence_split_mid_token():
    """The nastiest split: the fence itself broken in half."""
    text, payloads = collect(["Answer ```ic-pay", "load\n" + json.dumps(PAYLOAD) + "\n```", " done"])
    assert text == "Answer  done"
    assert len(payloads) == 1


@pytest.mark.parametrize("size", [1, 2, 3, 7, 13, 64])
def test_arbitrary_chunk_sizes(size):
    stream = f"Here is the result. {BLOCK} That is all."
    chunks = [stream[i:i + size] for i in range(0, len(stream), size)]
    text, payloads = collect(chunks)
    assert text == "Here is the result.  That is all."
    assert len(payloads) == 1
    assert payloads[0]["payload"] == PAYLOAD


def test_character_by_character():
    """One character per chunk -- the worst case a transport can produce."""
    stream = f"A{BLOCK}B"
    text, payloads = collect(list(stream))
    assert text == "AB"
    assert len(payloads) == 1


def test_multiple_payloads():
    second = dict(PAYLOAD, tool="calculate_savings")
    block2 = "```ic-payload\n" + json.dumps(second) + "\n```"
    text, payloads = collect([f"one {BLOCK} two {block2} three"])
    assert text == "one  two  three"
    assert [p["name"] for p in payloads] == ["calculate_mortgage", "calculate_savings"]


def test_backticks_that_are_not_a_payload_fence_survive():
    text, payloads = collect(["Use ```python\nprint(1)\n``` for that."])
    assert text == "Use ```python\nprint(1)\n``` for that."
    assert payloads == []


def test_malformed_json_is_dropped_without_losing_prose():
    bad = "```ic-payload\n{not valid json}\n```"
    text, payloads = collect([f"Before {bad} after"])
    assert text == "Before  after"
    assert payloads == []


def test_non_object_payload_is_dropped():
    arr = "```ic-payload\n[1,2,3]\n```"
    text, payloads = collect([f"x {arr} y"])
    assert text == "x  y"
    assert payloads == []


def test_unterminated_fence_is_discarded_not_emitted_as_prose():
    """A truncated stream must not dump raw JSON into the user's transcript."""
    text, payloads = collect(["Answer ```ic-payload\n{\"tool\":\"x\",\"summary\":{}"])
    assert text == "Answer "
    assert payloads == []


def test_no_partial_fence_leaks_when_stream_ends_on_backticks():
    text, payloads = collect(["Done ``"])
    assert text == "Done ``"      # flushed verbatim; it was never a fence
    assert payloads == []


def test_payload_with_no_tool_name_still_reports_something():
    block = "```ic-payload\n" + json.dumps({"summary": {}}) + "\n```"
    _, payloads = collect([block])
    assert payloads[0]["name"] == "tool"


def test_strip_payloads_helper():
    assert strip_payloads(f"a {BLOCK} b") == "a  b"


def test_large_payload_survives_realistic_chunking():
    big = {"tool": "compare_mortgage_options",
           "charts": [{"id": "c", "data": [{"x": i, "s0": i * 1.5} for i in range(400)]}]}
    block = "```ic-payload\n" + json.dumps(big) + "\n```"
    stream = f"Comparison: {block} done"
    chunks = [stream[i:i + 97] for i in range(0, len(stream), 97)]
    text, payloads = collect(chunks)
    assert text == "Comparison:  done"
    assert len(payloads[0]["payload"]["charts"][0]["data"]) == 400
