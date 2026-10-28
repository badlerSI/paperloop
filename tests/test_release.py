"""What publishing needs: the skill zip for claude.ai uploads, and what the plugin directory checks."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugin"
sys.path.insert(0, str(ROOT / "devtools"))
sys.path.insert(0, str(PLUGIN / "skills" / "paper-loop" / "scripts"))

import release  # noqa: E402
from paper_loop_core import sources as SR  # noqa: E402


def front_matter(text: str) -> dict:
    """SKILL.md's front matter, checked the way a YAML parser reads it: a bare value can't hold ": " or " #"
    (or start with a YAML indicator), so a value that does is a quoted string."""
    head = text.split("\n---\n")[0].removeprefix("---\n")
    out = {}
    for line in head.splitlines():
        key, value = line.split(": ", 1)
        if value.startswith('"'):
            value = json.loads(value)
        else:
            assert ": " not in value and " #" not in value and value[:1] not in "'[{&*!|>%@`", line
        out[key] = value
    return out


def test_skill_zip_holds_the_folder_with_a_short_description(tmp_path):
    with zipfile.ZipFile(release.build(tmp_path)) as z:
        names = z.namelist()
        skill_md = z.read("paper-loop/SKILL.md").decode()
    assert all(n.startswith("paper-loop/") for n in names)  # the folder itself, not its contents
    assert "paper-loop/scripts/paper_loop.py" in names
    assert not [n for n in names if "__pycache__" in n or n.endswith((".pyc", ".DS_Store"))]
    ours = front_matter(skill_md)
    assert ours["name"] == "paper-loop" and ours["description"] == release.SHORT
    assert len(release.SHORT) <= 200  # claude.ai's upload limit
    plugin_md = (PLUGIN / "skills" / "paper-loop" / "SKILL.md").read_text()
    assert skill_md.split("\n---\n", 1)[1] == plugin_md.split("\n---\n", 1)[1]
    assert len(front_matter(plugin_md)["description"]) <= 1024


def test_plugin_folder_passes_the_directory_checks():
    readme = (PLUGIN / "README.md").read_text()
    prose = re.sub(r"```.*?```", "", readme, flags=re.S)
    assert len(prose.split()) >= 40
    assert len(re.findall(r'^- "', readme, re.M)) >= 3  # at least three example prompts
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    assert all(manifest.get(k) for k in ("name", "description", "version", "author", "license"))
    assert re.fullmatch(r"[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?", manifest["name"])
    tracked = subprocess.run(["git", "ls-files", "plugin"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    assert not [t for t in tracked if Path(t).name in (".DS_Store", "Thumbs.db", "desktop.ini")]
    big = [t for t in tracked if (ROOT / t).stat().st_size > 256 * 1024 and not t.endswith((".png", ".jpg"))]
    assert big == []  # held for a reviewer otherwise
    assert SR.AGENT.startswith(f"PaperLoop/{'.'.join(manifest['version'].split('.')[:2])} ")


def test_every_host_the_scripts_reach_is_disclosed():
    scripts = PLUGIN / "skills" / "paper-loop" / "scripts"
    code = "".join(p.read_text() for p in [scripts / "paper_loop.py", *(scripts / "paper_loop_core").glob("*.py")])
    assert "urlopen" not in code.replace((scripts / "paper_loop_core" / "sources.py").read_text(), "")
    assert re.findall(r"_get\(f?\"([^\"]*)", code) == ["https://{site}/w/api.php?{query}"]  # Wikimedia's API only
    hosts = set(re.findall(r'"((?:[a-z]+\.)+(?:wikipedia|wikisource)\.org)"', code))
    assert hosts == {"en.wikipedia.org", "simple.wikipedia.org", "en.wikisource.org"}
    for doc in (PLUGIN / "README.md", ROOT / "PRIVACY.md"):
        assert all(f"`{h}`" in doc.read_text() for h in hosts), doc.name
