from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"
TEXT_SUFFIXES = {".py", ".js", ".css", ".html", ".md", ".txt", ".yaml", ".yml"}
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__"}


def skip(path: Path) -> bool:
    if any(part in SKIP_DIRS for part in path.parts):
        return True
    # Workflow definitions are updated separately through the GitHub connector;
    # Actions tokens cannot mutate workflow files.
    return ".github/workflows" in path.as_posix()


def main() -> None:
    pairs: list[tuple[Path, Path]] = []
    for src in sorted(STATIC.glob("academy_*")):
        if not src.is_file():
            continue
        dst = src.with_name("cam_" + src.name[len("academy_"):])
        pairs.append((src, dst))

    mapping = {src.name: dst.name for src, dst in pairs}

    for src, dst in pairs:
        if dst.exists():
            raise RuntimeError(f"Refusing to overwrite existing target: {dst}")
        src.rename(dst)

    for path in sorted(ROOT.rglob("*")):
        if skip(path) or not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        updated = text
        for old, new in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True):
            updated = updated.replace(old, new)
        if updated != text:
            path.write_text(updated, encoding="utf-8")

    print(f"CAM-15 renamed {len(pairs)} static technical files and updated references.")


if __name__ == "__main__":
    main()
