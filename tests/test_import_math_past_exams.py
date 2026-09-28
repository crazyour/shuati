import pytest

from tools.import_math_past_exams import (
    EXTERNAL_MODEL_CONFIRMATION,
    parse_cli_args,
)


BASE_ARGS = ["--archive", "/tmp/archive", "--project", "/tmp/project"]


def test_provider_has_no_default(capsys):
    with pytest.raises(SystemExit) as exc_info:
        parse_cli_args(BASE_ARGS)

    assert exc_info.value.code == 2
    assert "--provider" in capsys.readouterr().err


@pytest.mark.parametrize("provider", ["claude", "minimax"])
def test_external_provider_requires_explicit_charge_confirmation(provider, capsys):
    with pytest.raises(SystemExit) as exc_info:
        parse_cli_args([*BASE_ARGS, "--provider", provider])

    assert exc_info.value.code == 2
    error = capsys.readouterr().err
    assert "Refusing to call an external model" in error
    assert EXTERNAL_MODEL_CONFIRMATION in error


@pytest.mark.parametrize("provider", ["claude", "minimax"])
def test_external_provider_is_enabled_only_with_exact_confirmation(provider):
    args = parse_cli_args([
        *BASE_ARGS,
        "--provider",
        provider,
        "--confirm-external-model-charges",
        EXTERNAL_MODEL_CONFIRMATION,
    ])

    assert args.provider == provider
    assert args.confirm_external_model_charges == EXTERNAL_MODEL_CONFIRMATION
