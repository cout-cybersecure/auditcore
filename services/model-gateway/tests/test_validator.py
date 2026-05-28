from auditcore_gateway.validator import extract_json, validate


def test_extracts_plain_json() -> None:
    assert extract_json('{"a": 1}') == {"a": 1}


def test_strips_markdown_fence() -> None:
    text = '```json\n{"a": 1}\n```'
    assert extract_json(text) == {"a": 1}


def test_finds_first_balanced_object() -> None:
    text = 'Sure! Here is the result: {"score": 7} — let me know.'
    assert extract_json(text) == {"score": 7}


def test_returns_none_on_garbage() -> None:
    assert extract_json("totally not json") is None


def test_validate_reports_path() -> None:
    schema = {
        "type": "object",
        "properties": {"a": {"type": "integer"}},
        "required": ["a"],
    }
    errs = validate({"a": "not-an-int"}, schema)
    assert errs
    assert errs[0].startswith("a: ")
