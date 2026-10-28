"""Build the skill zip for claude.ai's Customize > Skills upload, the way Free-plan users get Paper Loop.

    .venv/bin/python devtools/release.py [--out dist]

The zip holds the paper-loop/ folder itself, as the upload expects. The upload caps a skill's description
at 200 characters, so the zip's SKILL.md carries SHORT instead of the plugin's longer description; the rest
of the folder is the plugin's, byte for byte. Attach dist/paper-loop.zip to each GitHub release. Dev only,
never shipped.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "plugin" / "skills" / "paper-loop"
SHORT = ("Paper Loop for K-12 teachers: worksheets and lessons on paper, marked from a copier scan with a comment "
         "on every answer, then go-over slides, practice sheets, group work, games, and progress.")
SKIP = {"__pycache__", ".DS_Store", ".pytest_cache"}


def short_skill_md(text: str) -> str:
    """SKILL.md with its front matter's description replaced by SHORT."""
    head, sep, body = text.partition("\n---\n")
    if not text.startswith("---\n") or not sep:
        raise ValueError("SKILL.md has no front matter")
    quoted = json.dumps(SHORT, ensure_ascii=False)  # quoted: a ": " inside a bare YAML value doesn't parse
    lines = [f"description: {quoted}" if line.startswith("description:") else line for line in head.splitlines()]
    if not any(line.startswith("description:") for line in head.splitlines()):
        raise ValueError("SKILL.md's front matter has no description")
    return "\n".join(lines) + sep + body


def build(out: Path) -> Path:
    if len(SHORT) > 200:
        raise ValueError(f"SHORT is {len(SHORT)} characters; the upload allows 200")
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{SKILL.name}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(SKILL.rglob("*")):
            if path.is_dir() or SKIP & set(path.relative_to(SKILL).parts) or path.suffix == ".pyc":
                continue
            name = f"{SKILL.name}/{path.relative_to(SKILL).as_posix()}"
            if path == SKILL / "SKILL.md":
                z.writestr(name, short_skill_md(path.read_text()))
            else:
                z.write(path, name)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    zip_path = build(parser.parse_args().out)
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
    print(f"Wrote {zip_path}: {len(names)} files, {zip_path.stat().st_size / 1e6:.1f} MB")
