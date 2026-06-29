from __future__ import annotations

import hashlib
import sys
import zipfile
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = list(argv or sys.argv[1:])
    if len(args) != 3:
        print("Usage: package_release.py <app_dir> <zip_path> <sha256_path>")
        return 2

    app_dir = Path(args[0]).resolve()
    zip_path = Path(args[1]).resolve()
    sha_path = Path(args[2]).resolve()
    if not app_dir.is_dir():
        print(f"App dir not found: {app_dir}")
        return 1

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()
    if sha_path.exists():
        sha_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(app_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(app_dir).as_posix())

    digest = hashlib.sha256()
    with zip_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    sha_path.write_text(f"{digest.hexdigest()}  {zip_path.name}\n", encoding="ascii")
    print(f"Wrote {zip_path}")
    print(f"Wrote {sha_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
