"""Guardrail: the extractor must never see the golden set.

If gold labels reach extract/ (imported, read from disk, or pasted into a prompt
as few-shot examples), eval accuracy looks great and means nothing. Few-shot
examples belong in extract/examples/, written separately from evals/.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEAKS = re.compile(r"\bevals\b|\bgolden\b|\bgold/|\bgold_", re.I)


def test_extract_does_not_touch_evals():
    offenders = []
    for path in (REPO_ROOT / "extract").rglob("*"):
        if path.is_file() and path.suffix in {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml"}:
            for n, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if LEAKS.search(line):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{n}: {line.strip()[:80]}")
    assert not offenders, "extract/ must not reference evals/ or gold data:\n" + "\n".join(offenders)
