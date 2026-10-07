import pytest

from app.core.security import password_strength, validate_password_strength


@pytest.mark.parametrize("password", [
    "Zebra!Ax",
    "Rotta!Blu8",
    "New-password-2026",
])
def test_password_policy_accepts_good_passwords(password):
    result = password_strength(password)
    assert result["acceptable"] is True
    assert result["level"] in ("good", "strong")
    validate_password_strength(password)


@pytest.mark.parametrize("password,expected", [
    ("zebra!ax", "maiuscola"),
    ("ZEBRA!AX", "minuscola"),
    ("ZebraAx8", "speciale"),
    ("Short!A", "8 caratteri"),
    ("Password!", "comune"),
    ("Abcdef!Q9", "sequenze"),
    ("Aaaaaaa!", "ripetuti"),
])
def test_password_policy_rejects_missing_or_predictable_passwords(password, expected):
    result = password_strength(password)
    assert result["acceptable"] is False
    assert expected.lower() in result["message"].lower()
    with pytest.raises(ValueError):
        validate_password_strength(password)


def test_password_policy_blocks_company_username_and_email_context():
    context = ["Rossi Trasporti S.r.l.", "mrossi", "m.rossi@example.test"]
    for password in ("Rossi!Ax9", "Mrossi!A9", "Example!A9"):
        result = password_strength(password, context_values=context)
        assert result["acceptable"] is False
        assert "account" in result["message"].lower() or "azienda" in result["message"].lower()


def test_password_policy_rejects_outer_spaces_instead_of_silently_trimming():
    result = password_strength(" Rotta!Blu8")
    assert result["acceptable"] is False
    assert "spazi" in result["message"].lower()
