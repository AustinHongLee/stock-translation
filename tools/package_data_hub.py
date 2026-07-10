from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = ROOT / "dist" / "official_data"
DEFAULT_OUTPUT_DIR = ROOT / "dist"


def main() -> int:
    _configure_output()
    parser = argparse.ArgumentParser(description="Package the official data hub zip for GitHub Releases.")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    zip_path, sha_path, digest = package_data_hub(args.source_dir.resolve(), args.output_dir.resolve())
    print(f"Wrote {zip_path}")
    print(f"Wrote {sha_path}")
    print(f"sha256: {digest}")
    return 0


def package_data_hub(source_dir: Path, output_dir: Path) -> tuple[Path, Path, str]:
    manifest_path = source_dir / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"Official data manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    version = _manifest_version(manifest)
    if version <= 0:
        raise SystemExit("Official data manifest is missing data_snapshot_version.")

    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"StockTranslator-official-data-{version}.zip"
    sha_path = output_dir / f"{zip_path.name}.sha256"
    if zip_path.exists():
        zip_path.unlink()
    if sha_path.exists():
        sha_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir).as_posix())

    digest = _sha256(zip_path)
    sha_path.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    return zip_path, sha_path, digest


def _manifest_version(manifest: dict[str, Any]) -> int:
    try:
        return int(manifest.get("data_snapshot_version") or 0)
    except (TypeError, ValueError):
        return 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    raise SystemExit(main())
