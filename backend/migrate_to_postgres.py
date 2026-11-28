"""CLI utility to migrate local JSON/SQLite CMS data and OpenCV images to Neon PostgreSQL."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from cms_store import migrate_local_to_postgres  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate local CMS data (JSON/SQLite) and optimized images "
            "into a persistent PostgreSQL database (e.g. Neon free tier)."
        )
    )
    parser.add_argument(
        "--source",
        default=str(_BACKEND_DIR / "instance" / "cms_data.json"),
        help="Path to local cms_data.json or cms_data.sqlite3 file.",
    )
    parser.add_argument(
        "--uploads-dir",
        default=str(_BACKEND_DIR / "uploads" / "images"),
        help="Directory containing local WebP/JPEG uploads to store in PostgreSQL.",
    )
    parser.add_argument(
        "--database-url",
        default="",
        help="PostgreSQL connection string (defaults to MAHJAR_DATABASE_URL or DATABASE_URL).",
    )
    args = parser.parse_args(argv)

    database_url = (
        args.database_url
        or os.environ.get("MAHJAR_DATABASE_URL", "")
        or os.environ.get("DATABASE_URL", "")
    ).strip()
    if not database_url:
        print(
            "Error: provide --database-url or set MAHJAR_DATABASE_URL / DATABASE_URL.",
            file=sys.stderr,
        )
        return 1

    counts = migrate_local_to_postgres(
        args.source,
        database_url,
        uploads_dir=args.uploads_dir,
    )
    print(
        "Migration to PostgreSQL completed: "
        f"committee={counts['committee']}, "
        f"posts={counts['posts']}, "
        f"mediaLinks={counts['mediaLinks']}, "
        f"forms={counts['forms']}, "
        f"mediaAssets={counts['mediaAssets']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
