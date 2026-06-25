"""Lightweight JSON-schema validator for agent tool calls.

Only the schema keywords used by the project tools are supported:
type, required, properties, items, enum, minLength/maxLength,
minimum/maximum, minItems/maxItems, and additionalProperties.
"""

from __future__ import annotations

from typing import Any, Dict, List


StructuredError = Dict[str, Any]


def validate_tool_call(
    tool_name: str,
    tool_spec: Dict[str, Any],
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Validate one tool call.

    The legacy ``errors`` list is kept for existing callers/tests. The newer
    ``structured_errors`` list gives the LLM stable repair hints so it can
    recover from invalid calls without guessing from prose.
    """

    errors: List[str] = []
    structured_errors: List[StructuredError] = []

    if tool_spec is None:
        _add_error(
            errors,
            structured_errors,
            message=f"Tool {tool_name} has no registered schema",
            rule_id="missing_tool_spec",
            path=tool_name,
            reason=f"Tool {tool_name} has no registered schema.",
            suggested_fix="Choose a registered tool or register a parameter schema before calling it.",
        )
        return _result(errors, structured_errors)

    schema = tool_spec.get("parameters") or tool_spec.get("inputSchema") or {}
    if not isinstance(params, dict):
        actual_type = _json_type(params)
        _add_error(
            errors,
            structured_errors,
            message=f"Tool {tool_name} params must be object, got {actual_type}",
            rule_id="params_not_object",
            path=f"{tool_name}().params",
            reason=f"Tool parameters must be an object, got {actual_type}.",
            suggested_fix='Return params as a JSON object, for example {"path":"..."}.',
        )
        return _result(errors, structured_errors)

    _validate_object(schema, params, f"{tool_name}()", errors, structured_errors)
    return _result(errors, structured_errors)


def _result(errors: List[str], structured_errors: List[StructuredError]) -> Dict[str, Any]:
    return {
        "ok": not errors,
        "errors": errors,
        "structured_errors": structured_errors,
    }


def _add_error(
    errors: List[str],
    structured_errors: List[StructuredError],
    *,
    message: str,
    rule_id: str,
    path: str,
    reason: str,
    suggested_fix: str,
) -> None:
    errors.append(message)
    structured_errors.append({
        "rule_id": rule_id,
        "path": path,
        "reason": reason,
        "suggested_fix": suggested_fix,
    })


def _validate_object(
    schema: Dict[str, Any],
    value: Dict[str, Any],
    path: str,
    errors: List[str],
    structured_errors: List[StructuredError],
) -> None:
    if not isinstance(value, dict):
        actual_type = _json_type(value)
        _add_error(
            errors,
            structured_errors,
            message=f"{path} type mismatch: expected object, got {actual_type}",
            rule_id="type_mismatch",
            path=path,
            reason=f"Expected object at {path}, got {actual_type}.",
            suggested_fix=f"Provide {path} as a JSON object with the documented fields.",
        )
        return

    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        properties = {}
    required = schema.get("required", [])
    if not isinstance(required, list):
        required = []

    for key in required:
        if key not in value:
            param_path = f"{path}.{key}"
            expected_type = "any"
            if isinstance(properties.get(key), dict):
                expected_type = properties[key].get("type", "any")
            _add_error(
                errors,
                structured_errors,
                message=f"{path} missing required parameter '{key}'",
                rule_id="missing_required",
                path=param_path,
                reason=f"Missing required parameter '{key}'.",
                suggested_fix=f"Add params.{key} as {expected_type}.",
            )

    for key, sub_value in value.items():
        sub_path = f"{path}.{key}"
        if key not in properties:
            if schema.get("additionalProperties") is False:
                _add_error(
                    errors,
                    structured_errors,
                    message=f"{sub_path} is not an allowed parameter",
                    rule_id="unknown_parameter",
                    path=sub_path,
                    reason=f"Parameter '{key}' is not allowed for this tool.",
                    suggested_fix="Remove this field or choose a tool whose schema includes it.",
                )
            continue
        _validate_value(properties[key], sub_value, sub_path, errors, structured_errors)


def _validate_value(
    schema: Dict[str, Any],
    value: Any,
    path: str,
    errors: List[str],
    structured_errors: List[StructuredError],
) -> None:
    if not isinstance(schema, dict):
        return

    expected_type = schema.get("type")
    if expected_type and not _type_matches(expected_type, value):
        actual_type = _json_type(value)
        _add_error(
            errors,
            structured_errors,
            message=f"{path} type mismatch: expected {expected_type}, got {actual_type}",
            rule_id="type_mismatch",
            path=path,
            reason=f"Expected {expected_type} at {path}, got {actual_type}.",
            suggested_fix=f"Change {path} to a valid {expected_type} value.",
        )
        return

    if expected_type == "object":
        _validate_object(schema, value, path, errors, structured_errors)
    elif expected_type == "array":
        _validate_array(schema, value, path, errors, structured_errors)
    elif expected_type == "string":
        _validate_string(schema, value, path, errors, structured_errors)
    elif expected_type in ("number", "integer"):
        _validate_number(schema, value, path, errors, structured_errors)

    enum = schema.get("enum")
    if enum is not None and value not in enum:
        _add_error(
            errors,
            structured_errors,
            message=f"{path} value {value!r} is not in allowed enum {enum}",
            rule_id="enum_mismatch",
            path=path,
            reason=f"Value {value!r} is not one of the allowed enum values.",
            suggested_fix=f"Use one of: {', '.join(repr(item) for item in enum)}.",
        )


def _validate_array(
    schema: Dict[str, Any],
    value: List[Any],
    path: str,
    errors: List[str],
    structured_errors: List[StructuredError],
) -> None:
    items_schema = schema.get("items")
    if isinstance(items_schema, dict):
        for idx, item in enumerate(value):
            _validate_value(items_schema, item, f"{path}[{idx}]", errors, structured_errors)

    min_items = schema.get("minItems")
    if min_items is not None and len(value) < min_items:
        _add_error(
            errors,
            structured_errors,
            message=f"{path} needs at least {min_items} item(s)",
            rule_id="min_items",
            path=path,
            reason=f"Array must contain at least {min_items} item(s).",
            suggested_fix=f"Add items until {path} has at least {min_items} item(s).",
        )

    max_items = schema.get("maxItems")
    if max_items is not None and len(value) > max_items:
        _add_error(
            errors,
            structured_errors,
            message=f"{path} allows at most {max_items} item(s)",
            rule_id="max_items",
            path=path,
            reason=f"Array must contain at most {max_items} item(s).",
            suggested_fix=f"Remove items until {path} has at most {max_items} item(s).",
        )


def _validate_string(
    schema: Dict[str, Any],
    value: str,
    path: str,
    errors: List[str],
    structured_errors: List[StructuredError],
) -> None:
    min_len = schema.get("minLength")
    if min_len is not None and len(value) < min_len:
        _add_error(
            errors,
            structured_errors,
            message=f"{path} string length must be at least {min_len}",
            rule_id="min_length",
            path=path,
            reason=f"String must be at least {min_len} characters long.",
            suggested_fix=f"Provide a longer string for {path}.",
        )

    max_len = schema.get("maxLength")
    if max_len is not None and len(value) > max_len:
        _add_error(
            errors,
            structured_errors,
            message=f"{path} string length must be at most {max_len}",
            rule_id="max_length",
            path=path,
            reason=f"String must be at most {max_len} characters long.",
            suggested_fix=f"Shorten {path} to at most {max_len} characters.",
        )


def _validate_number(
    schema: Dict[str, Any],
    value: Any,
    path: str,
    errors: List[str],
    structured_errors: List[StructuredError],
) -> None:
    minimum = schema.get("minimum")
    if minimum is not None and value < minimum:
        _add_error(
            errors,
            structured_errors,
            message=f"{path} must be at least {minimum}",
            rule_id="minimum",
            path=path,
            reason=f"Number must be greater than or equal to {minimum}.",
            suggested_fix=f"Increase {path} to at least {minimum}.",
        )

    maximum = schema.get("maximum")
    if maximum is not None and value > maximum:
        _add_error(
            errors,
            structured_errors,
            message=f"{path} must be at most {maximum}",
            rule_id="maximum",
            path=path,
            reason=f"Number must be less than or equal to {maximum}.",
            suggested_fix=f"Decrease {path} to at most {maximum}.",
        )


def _type_matches(expected: str, value: Any) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return (isinstance(value, (int, float)) and not isinstance(value, bool))
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "null":
        return value is None
    return True


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__
