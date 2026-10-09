"""
Digital Twin AI — Input Validators

Reusable validation helpers for API route handlers.

These validators return simple values for easy use in route handlers:
- validate_required_fields: returns a list of missing field names (empty = valid)
- validate_positive_number: returns True if valid, False if not
- validate_enum: returns True if valid, False if not
- validate_data: returns (is_valid, errors_list) for comprehensive validation
"""


def validate_required_fields(data, fields):
    """
    Check that all required fields are present and non-empty.

    Args:
        data: Request data dict.
        fields: List of required field names.

    Returns:
        List of missing field names. Empty list if all present.
    """
    if not data:
        return fields

    missing = []
    for field in fields:
        value = data.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)

    return missing


def validate_positive_number(value):
    """
    Validate that a value is a non-negative number.

    Args:
        value: The value to validate.

    Returns:
        True if valid, False otherwise.
    """
    try:
        num = float(value)
        return num >= 0
    except (TypeError, ValueError):
        return False


def validate_enum(value, allowed_values):
    """
    Validate that a value is one of the allowed options (case-insensitive).

    Args:
        value: The value to validate.
        allowed_values: List of allowed values.

    Returns:
        True if valid, False otherwise.
    """
    if value is None:
        return False
    val_str = str(value).strip().lower()
    allowed_strs = [str(a).strip().lower() for a in allowed_values]
    return val_str in allowed_strs



def validate_data(data, schema):
    """
    Validate data against a schema definition.

    Schema format:
    {
        'field_name': {
            'required': True/False,
            'type': 'string'/'number'/'boolean',
            'enum': ['opt1', 'opt2'],  # optional
            'min': 0,                   # optional, for numbers
        }
    }

    Returns:
        (is_valid, errors_list) tuple.
    """
    errors = []

    if not data:
        return False, ["Request body is empty"]

    for field, rules in schema.items():
        value = data.get(field)

        # Check required
        if rules.get('required', False):
            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append(f"{field} is required")
                continue

        # Skip further validation if field is not provided and not required
        if value is None:
            continue

        # Check type
        expected_type = rules.get('type')
        if expected_type == 'number':
            try:
                float(value)
            except (TypeError, ValueError):
                errors.append(f"{field} must be a valid number")
                continue

            if 'min' in rules and float(value) < rules['min']:
                errors.append(f"{field} must be at least {rules['min']}")

        elif expected_type == 'boolean':
            if not isinstance(value, bool):
                errors.append(f"{field} must be a boolean")

        # Check enum
        if 'enum' in rules and value not in rules['enum']:
            errors.append(f"{field} must be one of: {', '.join(str(v) for v in rules['enum'])}")

    return len(errors) == 0, errors
