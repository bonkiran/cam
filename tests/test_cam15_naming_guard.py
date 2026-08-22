from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_active_cam_namespace_has_no_legacy_academy_technical_references():
    forbidden_filenames = []
    for folder, pattern in [
        (ROOT / "app", "academy_*.py"),
        (ROOT / "app" / "static", "academy_*.js"),
        (ROOT / "app" / "static", "academy_*.css"),
        (ROOT / "app" / "static", "academy_*.html"),
        (ROOT / "tests", "test_academy_*.py"),
    ]:
        forbidden_filenames.extend(str(p.relative_to(ROOT)) for p in folder.glob(pattern))
    assert not forbidden_filenames, f"Legacy technical filenames remain: {forbidden_filenames}"

    forbidden_patterns = ("/api/academy", "#academy", "academyWorkspace", "academy-content", "academy-route-pending")
    checked_roots = [ROOT / "app" / "static", ROOT / "tests", ROOT / "run.py"]
    offenders = []
    for checked in checked_roots:
        paths = [checked] if checked.is_file() else [p for p in checked.rglob("*") if p.is_file() and p.suffix in {".py", ".js", ".css", ".html"}]
        for file in paths:
            text = file.read_text(encoding="utf-8", errors="ignore")
            for pattern in forbidden_patterns:
                if pattern in text:
                    offenders.append(f"{file.relative_to(ROOT)} -> {pattern}")
    assert not offenders, "Legacy active namespace references remain:\n" + "\n".join(offenders[:100])


def test_cam_route_and_api_are_present():
    index = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    shell_files = list((ROOT / "app" / "static").glob("cam_*shell*.js"))
    assert shell_files, "CAM shell implementation is missing"
    assert "/api/cam" in "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in (ROOT / "app" / "static").glob("cam_*.js"))
    assert "/static/cam_" in index
