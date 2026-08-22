from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# CAM-15 is a technical namespace migration. Business-facing phrases such as
# "Cricket Academy" remain valid product language. Persisted database names
# (academies, academy_id, academy_sessions, academy_users, etc.) are deliberately
# NOT renamed in this pass because that requires a controlled data migration.

TEXT_SUFFIXES = {".py", ".js", ".css", ".html", ".yml", ".yaml", ".md", ".txt"}
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__"}


def should_skip(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def rename_candidates() -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []

    # Python application modules: academy_foo.py -> cam_foo.py
    for src in sorted((ROOT / "app").glob("academy_*.py")):
        pairs.append((src, src.with_name("cam_" + src.name[len("academy_") :])))

    # Static implementation files: academy_foo.{js,css,html} -> cam_foo.*
    for suffix in ("*.js", "*.css", "*.html"):
        for src in sorted((ROOT / "app" / "static").glob(f"academy_{suffix[2:]}")):
            pairs.append((src, src.with_name("cam_" + src.name[len("academy_") :])))

    # Test modules: test_academy_foo.py -> test_cam_foo.py
    for src in sorted((ROOT / "tests").glob("test_academy_*.py")):
        pairs.append((src, src.with_name("test_cam_" + src.name[len("test_academy_") :])))

    # Workflow names are code/navigation metadata too.
    workflows = ROOT / ".github" / "workflows"
    if workflows.exists():
        for src in sorted(workflows.glob("academy-*.yml")):
            pairs.append((src, src.with_name("cam-" + src.name[len("academy-") :])))

    # Utility scripts should use CAM terminology as well.
    scripts_dir = ROOT / "scripts"
    if scripts_dir.exists():
        for src in sorted(scripts_dir.glob("*academy*.py")):
            if src.name == Path(__file__).name:
                continue
            pairs.append((src, src.with_name(src.name.replace("academy", "cam"))))

    # Historical planning documents are retained, but under CAM names.
    for src in sorted(ROOT.glob("ACADEMY_*.md")):
        pairs.append((src, src.with_name("CAM_" + src.name[len("ACADEMY_") :])))

    # Deduplicate defensively.
    seen: set[Path] = set()
    out: list[tuple[Path, Path]] = []
    for src, dst in pairs:
        if src in seen:
            continue
        seen.add(src)
        out.append((src, dst))
    return out


def build_token_mapping(pairs: list[tuple[Path, Path]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for src, dst in pairs:
        mapping[src.name] = dst.name
        # Module/test/workflow stem references often omit the extension.
        if src.suffix in {".py", ".js", ".css", ".html", ".yml"}:
            mapping[src.stem] = dst.stem
        try:
            old_rel = src.relative_to(ROOT).as_posix()
            new_rel = dst.relative_to(ROOT).as_posix()
            mapping[old_rel] = new_rel
        except ValueError:
            pass
    return mapping


def transform_text(text: str, token_mapping: dict[str, str]) -> str:
    # First update exact file/module references, longest tokens first to avoid
    # short names partially rewriting longer ones.
    for old in sorted(token_mapping, key=len, reverse=True):
        text = text.replace(old, token_mapping[old])

    # Active HTTP namespace: CAM owns /api/cam. A legacy bridge keeps old clients
    # working temporarily, but current code must not emit /api/academy.
    text = text.replace("/api/academy", "/api/cam")

    # Active SPA namespace: the original CrickAnalysis video dashboard already
    # owns #dashboard, so CAM's clean top-level route is #cam.
    text = text.replace("#academy", "#cam")
    text = re.sub(r"(['\"])academy(\?[^'\"]*)?\1", lambda m: f"{m.group(1)}cam{m.group(2) or ''}{m.group(1)}", text)

    # DOM/CSS technical namespace. Capitalized user-facing words such as
    # "Academy Name" are intentionally untouched.
    text = text.replace("academyWorkspace", "camWorkspace")
    text = text.replace("academy-content", "cam-content")
    text = text.replace("academy-route-pending", "cam-route-pending")
    text = text.replace("academy-", "cam-")
    text = re.sub(r"\bacademy([A-Z][A-Za-z0-9_]*)", lambda m: "cam" + m.group(1), text)
    text = re.sub(r"\bAcademy([A-Z][A-Za-z0-9_]*)", lambda m: "Cam" + m.group(1), text)

    return text


def add_legacy_api_bridge() -> None:
    path = ROOT / "app" / "cam_api_legacy_bridge.py"
    path.write_text(
        '''from __future__ import annotations\n\n\nclass CamLegacyApiBridge:\n    """Temporary transport bridge for pre-CAM /api/academy clients.\n\n    Current application code uses /api/cam. Persisted external bookmarks or old\n    test clients can still call /api/academy during the migration window; those\n    requests are rewritten before authorization and route matching.\n    """\n\n    def __init__(self, app):\n        self.app = app\n\n    async def __call__(self, scope, receive, send):\n        if scope.get("type") == "http":\n            path = str(scope.get("path") or "")\n            if path == "/api/academy" or path.startswith("/api/academy/"):\n                suffix = path[len("/api/academy") :]\n                scope = dict(scope)\n                scope["path"] = "/api/cam" + suffix\n                scope["raw_path"] = scope["path"].encode("utf-8")\n        await self.app(scope, receive, send)\n\n\ndef install_cam_legacy_api_bridge(app) -> None:\n    app.add_middleware(CamLegacyApiBridge)\n''',
        encoding="utf-8",
    )


def patch_run_py() -> None:
    path = ROOT / "run.py"
    text = path.read_text(encoding="utf-8")
    import_line = "from app.cam_api_legacy_bridge import install_cam_legacy_api_bridge\n"
    if import_line not in text:
        marker = "from app.system_api import router as system_router\n"
        text = text.replace(marker, marker + import_line)

    call_line = "install_cam_legacy_api_bridge(app)\n"
    if call_line not in text:
        marker = "install_cam_management_rbac(app)\n"
        if marker not in text:
            # The function may still carry its old name before token rewrite.
            marker = "install_academy_management_rbac(app)\n"
        text = text.replace(marker, marker + call_line)
    path.write_text(text, encoding="utf-8")


def write_guard_test() -> None:
    path = ROOT / "tests" / "test_cam15_naming_guard.py"
    path.write_text(
        '''from pathlib import Path\n\nROOT = Path(__file__).resolve().parents[1]\n\n\ndef test_active_cam_namespace_has_no_legacy_academy_technical_references():\n    # Persisted SQL schema names are intentionally outside this guard. The guard\n    # protects active route/module/static naming, which is what users and future\n    # CAM development should build against.\n    forbidden_filenames = []\n    for folder, pattern in [\n        (ROOT / "app", "academy_*.py"),\n        (ROOT / "app" / "static", "academy_*.js"),\n        (ROOT / "app" / "static", "academy_*.css"),\n        (ROOT / "app" / "static", "academy_*.html"),\n        (ROOT / "tests", "test_academy_*.py"),\n        (ROOT / ".github" / "workflows", "academy-*.yml"),\n    ]:\n        forbidden_filenames.extend(str(p.relative_to(ROOT)) for p in folder.glob(pattern))\n    assert not forbidden_filenames, f"Legacy technical filenames remain: {forbidden_filenames}"\n\n    forbidden_patterns = ("/api/academy", "#academy", "academyWorkspace", "academy-content", "academy-route-pending")\n    checked_roots = [ROOT / "app" / "static", ROOT / "tests", ROOT / "run.py"]\n    offenders = []\n    for checked in checked_roots:\n        paths = [checked] if checked.is_file() else [p for p in checked.rglob("*") if p.is_file() and p.suffix in {".py", ".js", ".css", ".html"}]\n        for file in paths:\n            text = file.read_text(encoding="utf-8", errors="ignore")\n            for pattern in forbidden_patterns:\n                if pattern in text:\n                    offenders.append(f"{file.relative_to(ROOT)} -> {pattern}")\n    assert not offenders, "Legacy active namespace references remain:\\n" + "\\n".join(offenders[:100])\n\n\ndef test_cam_route_and_api_are_present():\n    index = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")\n    shell_files = list((ROOT / "app" / "static").glob("cam_*shell*.js"))\n    assert shell_files, "CAM shell implementation is missing"\n    shell = "\\n".join(p.read_text(encoding="utf-8") for p in shell_files)\n    assert "cam" in shell\n    assert "/api/cam" in "\\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in (ROOT / "app" / "static").glob("cam_*.js"))\n    assert "/static/cam_" in index\n''',
        encoding="utf-8",
    )


def main() -> None:
    pairs = rename_candidates()
    mapping = build_token_mapping(pairs)

    # Apply filename migrations first.
    for src, dst in pairs:
        if not src.exists():
            continue
        if dst.exists() and dst != src:
            raise RuntimeError(f"Refusing to overwrite existing cleanup target: {dst}")
        src.rename(dst)

    # Transform all text after renaming so imports, workflow paths, static
    # references and route/DOM namespaces remain consistent in one commit.
    for path in sorted(ROOT.rglob("*")):
        if should_skip(path) or not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        updated = transform_text(text, mapping)
        if updated != text:
            path.write_text(updated, encoding="utf-8")

    add_legacy_api_bridge()
    patch_run_py()
    write_guard_test()

    print(f"CAM-15 renamed {len(pairs)} technical files and normalized active CAM namespace.")


if __name__ == "__main__":
    main()
