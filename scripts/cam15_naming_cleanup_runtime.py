from __future__ import annotations

from pathlib import Path

import cam15_naming_cleanup as base

ROOT = Path(__file__).resolve().parents[1]
_original_candidates = base.rename_candidates


def runtime_candidates():
    """Run the product/code rename without touching Actions workflow files.

    GitHub's Actions token cannot rename workflow definitions. Those files are
    handled separately through the GitHub connector after the runtime migration
    lands, so they cannot block the CAM application cleanup.
    """
    return [
        (src, dst)
        for src, dst in _original_candidates()
        if ".github/workflows" not in src.as_posix()
    ]


def write_runtime_guard() -> None:
    path = ROOT / "tests" / "test_cam15_naming_guard.py"
    path.write_text(
        '''from pathlib import Path\n\nROOT = Path(__file__).resolve().parents[1]\n\n\ndef test_active_cam_namespace_has_no_legacy_academy_technical_references():\n    forbidden_filenames = []\n    for folder, pattern in [\n        (ROOT / "app", "academy_*.py"),\n        (ROOT / "app" / "static", "academy_*.js"),\n        (ROOT / "app" / "static", "academy_*.css"),\n        (ROOT / "app" / "static", "academy_*.html"),\n        (ROOT / "tests", "test_academy_*.py"),\n    ]:\n        forbidden_filenames.extend(str(p.relative_to(ROOT)) for p in folder.glob(pattern))\n    assert not forbidden_filenames, f"Legacy technical filenames remain: {forbidden_filenames}"\n\n    forbidden_patterns = ("/api/academy", "#academy", "academyWorkspace", "academy-content", "academy-route-pending")\n    checked_roots = [ROOT / "app" / "static", ROOT / "tests", ROOT / "run.py"]\n    offenders = []\n    for checked in checked_roots:\n        paths = [checked] if checked.is_file() else [p for p in checked.rglob("*") if p.is_file() and p.suffix in {".py", ".js", ".css", ".html"}]\n        for file in paths:\n            text = file.read_text(encoding="utf-8", errors="ignore")\n            for pattern in forbidden_patterns:\n                if pattern in text:\n                    offenders.append(f"{file.relative_to(ROOT)} -> {pattern}")\n    assert not offenders, "Legacy active namespace references remain:\\n" + "\\n".join(offenders[:100])\n\n\ndef test_cam_route_and_api_are_present():\n    index = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")\n    shell_files = list((ROOT / "app" / "static").glob("cam_*shell*.js"))\n    assert shell_files, "CAM shell implementation is missing"\n    assert "/api/cam" in "\\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in (ROOT / "app" / "static").glob("cam_*.js"))\n    assert "/static/cam_" in index\n''',
        encoding="utf-8",
    )


base.rename_candidates = runtime_candidates
base.write_guard_test = write_runtime_guard
base.main()
