"""The synthetic outcome column must not appear anywhere in src/ except the generator and validation."""
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
ALLOWED = {"generate_data.py", "validation.py"}
FORBIDDEN = "true_bad"


def test_true_bad_is_confined_to_generator_and_validation():
    files = [p for p in SRC.rglob("*.py") if p.name not in ALLOWED]
    assert files, "no source files found — is the path right?"
    offenders = [str(p.relative_to(SRC)) for p in files if FORBIDDEN in p.read_text(encoding="utf-8")]
    assert offenders == [], f"'{FORBIDDEN}' referenced in: {offenders}"
