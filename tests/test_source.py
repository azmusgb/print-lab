"""`lab source`: read how Bambu Studio itself uses a setting, at the tag that matches the installed slicer."""
import json
import subprocess

import pytest

from lab import source


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def upstream(tmp_path, monkeypatch):
    repo = tmp_path / "BambuStudio"
    (repo / "src" / "libslic3r").mkdir(parents=True)
    (repo / "src" / "libslic3r" / "GCode.cpp").write_text(
        "// speeds\ndouble cap = max_volumetric_speed / (width * height);\nreturn std::min(speed, cap);\n")
    (repo / "README.md").write_text("max_volumetric_speed is documented elsewhere\n")
    _git(repo, "init", "-q")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "add", ".")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x")
    _git(repo, "tag", "v02.08.02.61")
    monkeypatch.setenv("LAB_BAMBU_SOURCE_REPO", str(repo))
    monkeypatch.setenv("LAB_SOURCE_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(source, "CAP_DIR", tmp_path / "capabilities")
    return repo


def test_lookup_reads_the_tag_that_matches_the_installed_slicer(upstream):
    r = source.lookup("max_volumetric_speed", version="02.08.02.61")
    assert r["tag"] == "v02.08.02.61"
    assert [(h["path"], h["line"]) for h in r["hits"]] == [("src/libslic3r/GCode.cpp", 2)]  # src/ only
    assert "std::min" in r["hits"][0]["context"]
    assert r["hits"][0]["url"] == ("https://github.com/bambulab/BambuStudio/blob/v02.08.02.61/"
                                   "src/libslic3r/GCode.cpp#L2")


def test_the_checkout_is_kept_so_later_lookups_need_no_network(upstream):
    import shutil
    source.lookup("max_volumetric_speed", version="02.08.02.61")
    shutil.rmtree(upstream)
    assert source.lookup("cap", version="02.08.02.61")["hits"]


def test_a_version_with_no_tag_says_so(upstream):
    with pytest.raises(ValueError, match="v09.09.09.99"):
        source.lookup("x", version="09.09.09.99")


def test_a_note_records_the_finding_against_the_slicer_version(upstream):
    r = source.lookup("max_volumetric_speed", version="02.08.02.61", note="speed is capped by flow")
    saved = json.loads((source.CAP_DIR / "02.08.02.61-source.json").read_text())
    assert saved[-1]["term"] == "max_volumetric_speed" and saved[-1]["note"] == "speed is capped by flow"
    assert saved[-1]["hits"] == ["src/libslic3r/GCode.cpp:2"] and saved[-1]["tag"] == r["tag"]
