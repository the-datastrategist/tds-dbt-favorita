import pytest

from scripts.bootstrap_gcp import destructive_changes, parse_terraform_console_value


def test_parse_terraform_console_value_ignores_progress_messages() -> None:
    output = 'Acquiring state lock. This may take a few moments...\n"\\"favorita\\""\n'

    assert parse_terraform_console_value(output) == "favorita"


def test_parse_terraform_console_value_rejects_missing_json() -> None:
    with pytest.raises(RuntimeError, match="returned no JSON value"):
        parse_terraform_console_value("Acquiring state lock...")


def test_destructive_changes_accepts_create_and_update() -> None:
    document = {
        "resource_changes": [
            {"address": "example.create", "change": {"actions": ["create"]}},
            {"address": "example.update", "change": {"actions": ["update"]}},
            {"address": "example.noop", "change": {"actions": ["no-op"]}},
        ]
    }

    assert destructive_changes(document) == []


def test_destructive_changes_rejects_delete_and_replace() -> None:
    document = {
        "resource_changes": [
            {"address": "example.delete", "change": {"actions": ["delete"]}},
            {
                "address": "example.replace",
                "change": {"actions": ["delete", "create"]},
            },
        ]
    }

    assert destructive_changes(document) == [
        "example.delete: ['delete']",
        "example.replace: ['delete', 'create']",
    ]
