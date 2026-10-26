from collusiongen.agents.parsing import parse_action, strip_reasoning


def test_last_json_object_wins():
    assert parse_action('I think {"price": 1} no wait {"price": 2}') == {"price": 2}


def test_fenced_block_preferred():
    text = 'plan {"x": 0}\n```json\n{"price": 3.5}\n```'
    assert parse_action(text) == {"price": 3.5}


def test_braces_inside_strings():
    assert parse_action('{"message": "use {curly} braces"}') == {"message": "use {curly} braces"}


def test_reasoning_is_stripped():
    answer, reasoning = strip_reasoning('<think>{"price": 99}</think>{"price": 1}')
    assert parse_action(answer) == {"price": 1}
    assert "99" in reasoning


def test_garbage_returns_none():
    assert parse_action("no json here") is None
    assert parse_action("{not json}") is None


def test_bare_closing_tag_splits_reasoning():
    text = 'Maybe {"price": 99} is good... no.</ifm|think>{"price": 1}'
    _, reasoning = strip_reasoning(text)
    assert parse_action(text) == {"price": 1} and "99" in reasoning
    # JSON only in the reasoning, plain answer after the tag: no action, not the reasoning's JSON
    assert parse_action('try {"answer": "1"} ok</ifm|think_faster>5,074,979') is None
