"""Tool calls come from a small model's raw output, so every call is validated first."""

import json

import pytest

from echo.tools.registry import ToolRegistry


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry(max_output_chars=100)
    reg.register(
        name="add",
        description="Add two integers.",
        parameters={
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            "required": ["a", "b"],
        },
        handler=lambda a, b: a + b,
    )
    reg.register(
        name="shout",
        description="Upper-case a string.",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}, "loud": {"type": "boolean"}},
            "required": ["text"],
        },
        handler=lambda text, loud=False: text.upper() + ("!" if loud else ""),
        requires_confirmation=True,
    )
    reg.register(
        name="boom",
        description="Always fails.",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=lambda: 1 / 0,
    )
    reg.register(
        name="wall",
        description="Returns a very long string.",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=lambda: "x" * 500,
    )
    return reg


def test_unknown_tool_lists_the_available_ones(registry):
    ok, args, error = registry.validate_and_parse_args("rm_rf", "{}")
    assert not ok and args is None
    assert "Unknown tool" in error and "add" in error


def test_invalid_json_is_reported(registry):
    ok, _, error = registry.validate_and_parse_args("add", '{"a": 1,')
    assert not ok and "Invalid JSON" in error


def test_arguments_must_be_an_object(registry):
    ok, _, error = registry.validate_and_parse_args("add", "[1, 2]")
    assert not ok and "JSON object" in error


def test_missing_required_parameter(registry):
    ok, _, error = registry.validate_and_parse_args("add", json.dumps({"a": 1}))
    assert not ok and "Missing required parameter" in error and "b" in error


def test_undeclared_parameters_are_rejected(registry):
    ok, _, error = registry.validate_and_parse_args("add", json.dumps({"a": 1, "b": 2, "c": 3}))
    assert not ok and "Unknown parameter" in error


def test_numbers_sent_as_strings_are_accepted(registry):
    ok, args, _ = registry.validate_and_parse_args("add", json.dumps({"a": "2", "b": "3"}))
    assert ok and args == {"a": 2, "b": 3}


@pytest.mark.parametrize("value", ["3.5", "abc", True, None, [1]])
def test_values_that_are_not_integers_are_rejected(registry, value):
    ok, _, error = registry.validate_and_parse_args("add", json.dumps({"a": value, "b": 1}))
    assert not ok and "Invalid value for parameter 'a'" in error


def test_booleans_sent_as_text_are_accepted(registry):
    ok, args, _ = registry.validate_and_parse_args("shout", json.dumps({"text": "hi", "loud": "TRUE"}))
    assert ok and args["loud"] is True


def test_execute_runs_the_handler(registry):
    record = registry.execute("call-1", "add", '{"a": 2, "b": 5}')
    assert record.success and record.result == "7" and record.error is None
    assert registry.execution_history[-1] is record


def test_execute_turns_handler_errors_into_a_failed_record(registry):
    record = registry.execute("call-2", "boom", "{}")
    assert not record.success
    assert "ZeroDivisionError" in record.result


def test_execute_does_not_run_a_call_that_fails_validation(registry):
    record = registry.execute("call-3", "add", '{"a": 1}')
    assert not record.success and record.arguments == {}
    assert record.result.startswith("Error:")


def test_long_output_is_truncated(registry):
    record = registry.execute("call-4", "wall", "{}")
    assert record.success
    assert len(record.result) < 500
    assert "Output truncated" in record.result


def test_confirmation_flag_is_per_tool(registry):
    assert registry.requires_confirmation("shout")
    assert not registry.requires_confirmation("add")
    assert not registry.requires_confirmation("does-not-exist")


def test_registering_the_same_tool_twice_fails(registry):
    with pytest.raises(ValueError):
        registry.register("add", "again", {"type": "object", "properties": {}}, handler=lambda: None)


def test_definitions_follow_the_openai_tool_format(registry):
    definitions = registry.get_tool_definitions()
    assert {d["function"]["name"] for d in definitions} == {"add", "shout", "boom", "wall"}
    assert all(d["type"] == "function" for d in definitions)
