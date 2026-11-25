"""Thread-safe JSON and SQLite CMS stores for committee, posts, media links, and forms."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
from typing import Any
from urllib.parse import unquote, urlsplit

ALLOWED_FORM_TYPES = ("feedback", "help_request", "event_registration")

DEFAULT_GOOGLE_FORMS = [
    {
        "id": 1,
        "formType": "feedback",
        "title": "نموذج إبداء الرأي والمقترحات العامة",
        "description": "نرحب بآرائكم ومقترحاتكم لتطوير البيئة التعليمية والأنشطة المدرسية.",
        "canonicalUrl": "https://docs.google.com/forms/d/e/1FAIpQLScMahjarFeedbackDefault01/viewform",
        "embedUrl": "https://docs.google.com/forms/d/e/1FAIpQLScMahjarFeedbackDefault01/viewform?embedded=true",
        "provider": "google_forms",
        "formId": "1FAIpQLScMahjarFeedbackDefault01",
        "active": True,
        "displayOrder": 1,
    },
    {
        "id": 2,
        "formType": "help_request",
        "title": "نموذج طرح مشكلة عامة أو طلب مساعدة",
        "description": "لتقديم الملاحظات العامة حول محيط المدرسة أو طلب مساندة من اللجنة.",
        "canonicalUrl": "https://docs.google.com/forms/d/e/1FAIpQLScMahjarHelpRequestDefault02/viewform",
        "embedUrl": "https://docs.google.com/forms/d/e/1FAIpQLScMahjarHelpRequestDefault02/viewform?embedded=true",
        "provider": "google_forms",
        "formId": "1FAIpQLScMahjarHelpRequestDefault02",
        "active": True,
        "displayOrder": 2,
    },
    {
        "id": 3,
        "formType": "event_registration",
        "title": "استمارة التسجيل والمشاركة في الفعاليات المدرسية",
        "description": "سجّلوا للمشاركة أو التطوع في الفعاليات والأنشطة القادمة للمدرسة.",
        "canonicalUrl": "https://docs.google.com/forms/d/e/1FAIpQLScMahjarEventRegDefault03/viewform",
        "embedUrl": "https://docs.google.com/forms/d/e/1FAIpQLScMahjarEventRegDefault03/viewform?embedded=true",
        "provider": "google_forms",
        "formId": "1FAIpQLScMahjarEventRegDefault03",
        "active": True,
        "displayOrder": 3,
    },
]


class CMSStore:
    """In-memory and optional atomic JSON-persisted store for CMS entities."""

    def __init__(
        self,
        default_committee: list[dict[str, Any]],
        default_posts: list[dict[str, Any]],
        default_forms: list[dict[str, Any]] | None = None,
        data_file: str | Path | None = None,
    ):
        self._lock = threading.RLock()
        self._data_file = Path(data_file) if data_file else None
        self._data = self._load_or_seed(
            default_committee,
            default_posts,
            DEFAULT_GOOGLE_FORMS if default_forms is None else default_forms,
        )

    def _load_or_seed(
        self,
        default_committee: list[dict[str, Any]],
        default_posts: list[dict[str, Any]],
        default_forms: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if self._data_file and self._data_file.is_file():
            with self._data_file.open("r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            committee = loaded.get("committee", [])
            if not any("isDirectContact" in m for m in committee):
                for m in committee:
                    m["isDirectContact"] = m.get("fullName") == "طه علي اغباريه"
            posts = loaded.get("posts", [])
            media_links = loaded.get("media_links", [])
            forms = loaded.get("forms", [])
            next_ids = loaded.get("next_ids", {})
            return {
                "committee": committee,
                "posts": posts,
                "media_links": media_links,
                "forms": forms,
                "next_ids": {
                    "committee": int(
                        next_ids.get("committee")
                        or (max((int(r["id"]) for r in committee), default=0) + 1)
                    ),
                    "posts": int(
                        next_ids.get("posts")
                        or (max((int(r["id"]) for r in posts), default=0) + 1)
                    ),
                    "media_links": int(
                        next_ids.get("media_links")
                        or (max((int(r["id"]) for r in media_links), default=0) + 1)
                    ),
                    "forms": int(
                        next_ids.get("forms")
                        or (max((int(r["id"]) for r in forms), default=0) + 1)
                    ),
                },
            }

        seeded_committee = copy.deepcopy(default_committee)
        seeded_posts: list[dict[str, Any]] = []
        seeded_media_links: list[dict[str, Any]] = []
        next_link_id = 1

        for raw_post in copy.deepcopy(default_posts):
            embedded = raw_post.pop("mediaLinks", None) or []
            post_id = raw_post["id"]
            seeded_posts.append(raw_post)
            for link in embedded:
                if isinstance(link, dict):
                    entry = copy.deepcopy(link)
                    entry["id"] = next_link_id
                    entry["postId"] = post_id
                    seeded_media_links.append(entry)
                    next_link_id += 1

        seeded_forms = copy.deepcopy(default_forms)
        return {
            "committee": seeded_committee,
            "posts": seeded_posts,
            "media_links": seeded_media_links,
            "forms": seeded_forms,
            "next_ids": {
                "committee": max((int(r["id"]) for r in seeded_committee), default=0) + 1,
                "posts": max((int(r["id"]) for r in seeded_posts), default=0) + 1,
                "media_links": next_link_id,
                "forms": max((int(r["id"]) for r in seeded_forms), default=0) + 1,
            },
        }

    def _persist(self) -> None:
        if not self._data_file:
            return
        self._data_file.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=self._data_file.parent,
            prefix=".tmp_cms_",
            suffix=".json",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                json.dump(self._data, tmp_file, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._data_file)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def _allocate_id(self, collection: str) -> int:
        allocated = int(self._data["next_ids"][collection])
        self._data["next_ids"][collection] = allocated + 1
        return allocated

    def _hydrate_post(self, post: dict[str, Any]) -> dict[str, Any]:
        hydrated = copy.deepcopy(post)
        post_id = hydrated["id"]
        hydrated["mediaLinks"] = [
            copy.deepcopy(link)
            for link in self._data["media_links"]
            if link.get("postId") == post_id
        ]
        return hydrated

    def _replace_post_media_links(
        self, post_id: int, links: list[dict[str, Any]]
    ) -> None:
        self._data["media_links"] = [
            link for link in self._data["media_links"] if link.get("postId") != post_id
        ]
        for link in links:
            entry = copy.deepcopy(link)
            entry["id"] = self._allocate_id("media_links")
            entry["postId"] = post_id
            self._data["media_links"].append(entry)

    # --- Committee CRUD ---

    def list_committee(self) -> list[dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._data["committee"])

    def get_committee_member(self, member_id: int) -> dict[str, Any] | None:
        with self._lock:
            for member in self._data["committee"]:
                if member["id"] == member_id:
                    return copy.deepcopy(member)
            return None

    def create_committee_member(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            entry = copy.deepcopy(record)
            if entry.get("displayOrder") is None:
                existing_orders = [
                    int(m["displayOrder"])
                    for m in self._data["committee"]
                    if isinstance(m.get("displayOrder"), int)
                    and not isinstance(m.get("displayOrder"), bool)
                ]
                entry["displayOrder"] = (
                    max(existing_orders + [len(self._data["committee"])]) + 1
                )
            entry["id"] = self._allocate_id("committee")
            self._data["committee"].append(entry)
            self._persist()
            return copy.deepcopy(entry)

    def update_committee_member(
        self, member_id: int, updates: dict[str, Any]
    ) -> dict[str, Any] | None:
        with self._lock:
            for member in self._data["committee"]:
                if member["id"] == member_id:
                    member.update(copy.deepcopy(updates))
                    self._persist()
                    return copy.deepcopy(member)
            return None

    def delete_committee_member(self, member_id: int) -> bool:
        with self._lock:
            before = len(self._data["committee"])
            self._data["committee"] = [
                m for m in self._data["committee"] if m["id"] != member_id
            ]
            if len(self._data["committee"]) == before:
                return False
            self._persist()
            return True

    def reorder_committee(self, ordered_ids: list[int]) -> list[dict[str, Any]] | None:
        with self._lock:
            by_id = {int(member["id"]): member for member in self._data["committee"]}
            for mid in ordered_ids:
                if int(mid) not in by_id:
                    return None
            seen_ids = {int(mid) for mid in ordered_ids}
            ordered_members = [by_id[int(mid)] for mid in ordered_ids] + [
                member
                for member in self._data["committee"]
                if int(member["id"]) not in seen_ids
            ]
            for order_idx, member in enumerate(ordered_members, start=1):
                member["displayOrder"] = order_idx
            self._persist()
            return copy.deepcopy(ordered_members)

    # --- Posts CRUD ---

    def list_posts(self) -> list[dict[str, Any]]:
        with self._lock:
            return [self._hydrate_post(post) for post in self._data["posts"]]

    def get_post(self, post_id: int) -> dict[str, Any] | None:
        with self._lock:
            for post in self._data["posts"]:
                if post["id"] == post_id:
                    return self._hydrate_post(post)
            return None

    def create_post(
        self, record: dict[str, Any], media_links: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        with self._lock:
            entry = copy.deepcopy(record)
            entry.pop("mediaLinks", None)
            if entry.get("displayOrder") is None and any(
                p.get("displayOrder") is not None for p in self._data["posts"]
            ):
                for existing_post in self._data["posts"]:
                    if existing_post.get("displayOrder") is not None:
                        existing_post["displayOrder"] = int(existing_post["displayOrder"]) + 1
                entry["displayOrder"] = 1
            post_id = self._allocate_id("posts")
            entry["id"] = post_id
            self._data["posts"].append(entry)
            if media_links:
                self._replace_post_media_links(post_id, media_links)
            self._persist()
            return self._hydrate_post(entry)

    def update_post(
        self,
        post_id: int,
        updates: dict[str, Any],
        media_links: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            for post in self._data["posts"]:
                if post["id"] == post_id:
                    clean_updates = copy.deepcopy(updates)
                    clean_updates.pop("mediaLinks", None)
                    post.update(clean_updates)
                    if media_links is not None:
                        self._replace_post_media_links(post_id, media_links)
                    self._persist()
                    return self._hydrate_post(post)
            return None

    def delete_post(self, post_id: int) -> bool:
        with self._lock:
            before = len(self._data["posts"])
            self._data["posts"] = [
                p for p in self._data["posts"] if p["id"] != post_id
            ]
            if len(self._data["posts"]) == before:
                return False
            self._data["media_links"] = [
                link
                for link in self._data["media_links"]
                if link.get("postId") != post_id
            ]
            self._persist()
            return True

    def reorder_posts(self, ordered_ids: list[int]) -> list[dict[str, Any]] | None:
        with self._lock:
            by_id = {int(post["id"]): post for post in self._data["posts"]}
            for pid in ordered_ids:
                if int(pid) not in by_id:
                    return None
            seen_ids = {int(pid) for pid in ordered_ids}
            ordered_posts = [by_id[int(pid)] for pid in ordered_ids] + [
                post
                for post in self._data["posts"]
                if int(post["id"]) not in seen_ids
            ]
            for order_idx, post in enumerate(ordered_posts, start=1):
                post["displayOrder"] = order_idx
            self._persist()
            return [self._hydrate_post(post) for post in ordered_posts]

    # --- Media Links CRUD ---

    def list_media_links(self, post_id: int | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if post_id is None:
                return copy.deepcopy(self._data["media_links"])
            return [
                copy.deepcopy(link)
                for link in self._data["media_links"]
                if link.get("postId") == post_id
            ]

    def get_media_link(self, link_id: int) -> dict[str, Any] | None:
        with self._lock:
            for link in self._data["media_links"]:
                if link["id"] == link_id:
                    return copy.deepcopy(link)
            return None

    def create_media_link(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            entry = copy.deepcopy(record)
            entry["id"] = self._allocate_id("media_links")
            self._data["media_links"].append(entry)
            self._persist()
            return copy.deepcopy(entry)

    def update_media_link(
        self, link_id: int, updates: dict[str, Any]
    ) -> dict[str, Any] | None:
        with self._lock:
            for link in self._data["media_links"]:
                if link["id"] == link_id:
                    link.update(copy.deepcopy(updates))
                    self._persist()
                    return copy.deepcopy(link)
            return None

    def delete_media_link(self, link_id: int) -> bool:
        with self._lock:
            before = len(self._data["media_links"])
            self._data["media_links"] = [
                link for link in self._data["media_links"] if link["id"] != link_id
            ]
            if len(self._data["media_links"]) == before:
                return False
            self._persist()
            return True

    # --- Google Forms CRUD ---

    def list_forms(self) -> list[dict[str, Any]]:
        with self._lock:
            forms = copy.deepcopy(self._data["forms"])
            forms.sort(key=lambda item: (int(item.get("displayOrder") or 9999), int(item["id"])))
            return forms

    def get_form(self, form_id: int) -> dict[str, Any] | None:
        with self._lock:
            for form in self._data["forms"]:
                if form["id"] == form_id:
                    return copy.deepcopy(form)
            return None

    def create_form(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            entry = copy.deepcopy(record)
            if entry.get("displayOrder") is None:
                for existing_form in self._data["forms"]:
                    raw_order = existing_form.get("displayOrder")
                    if isinstance(raw_order, int) and not isinstance(raw_order, bool):
                        existing_form["displayOrder"] = int(raw_order) + 1
                entry["displayOrder"] = 1
            entry["id"] = self._allocate_id("forms")
            self._data["forms"].append(entry)
            self._persist()
            return copy.deepcopy(entry)

    def update_form(
        self, form_id: int, updates: dict[str, Any]
    ) -> dict[str, Any] | None:
        with self._lock:
            for form in self._data["forms"]:
                if form["id"] == form_id:
                    form.update(copy.deepcopy(updates))
                    self._persist()
                    return copy.deepcopy(form)
            return None

    def delete_form(self, form_id: int) -> bool:
        with self._lock:
            before = len(self._data["forms"])
            self._data["forms"] = [
                f for f in self._data["forms"] if f["id"] != form_id
            ]
            if len(self._data["forms"]) == before:
                return False
            self._persist()
            return True

    def reorder_forms(self, ordered_ids: list[int]) -> list[dict[str, Any]] | None:
        with self._lock:
            current_forms = self.list_forms()
            by_id = {int(form["id"]): form for form in self._data["forms"]}
            for fid in ordered_ids:
                if int(fid) not in by_id:
                    return None
            seen_ids = {int(fid) for fid in ordered_ids}
            ordered_forms = [by_id[int(fid)] for fid in ordered_ids] + [
                by_id[int(form["id"])]
                for form in current_forms
                if int(form["id"]) not in seen_ids
            ]
            for order_idx, form in enumerate(ordered_forms, start=1):
                form["displayOrder"] = order_idx
            self._persist()
            return self.list_forms()

    def export_snapshot(self) -> dict[str, Any]:
        """Return a deep-copied snapshot of all collections and sequence counters."""
        with self._lock:
            return copy.deepcopy(self._data)

    def storage_info(self) -> dict[str, Any]:
        """Return non-secret storage diagnostics for health/readiness reporting."""
        with self._lock:
            size_bytes = (
                self._data_file.stat().st_size
                if self._data_file and self._data_file.is_file()
                else 0
            )
            return {
                "backend": "json",
                "persisted": bool(self._data_file),
                "sizeBytes": int(size_bytes),
                "counts": {
                    "committee": len(self._data["committee"]),
                    "posts": len(self._data["posts"]),
                    "mediaLinks": len(self._data["media_links"]),
                    "forms": len(self._data["forms"]),
                },
            }


class SQLiteCMSStore:
    """Thread-safe SQLite-backed CMS store with WAL mode and JSON-store parity."""

    def __init__(
        self,
        default_committee: list[dict[str, Any]],
        default_posts: list[dict[str, Any]],
        default_forms: list[dict[str, Any]] | None = None,
        db_path: str | Path = ":memory:",
    ):
        self._lock = threading.RLock()
        raw_path = str(db_path).strip() if db_path is not None else ":memory:"
        self._is_memory = raw_path == ":memory:" or not raw_path
        self._db_path = None if self._is_memory else Path(raw_path)
        self._conn = self._open_connection()
        self._initialize_schema_and_seed(
            default_committee,
            default_posts,
            DEFAULT_GOOGLE_FORMS if default_forms is None else default_forms,
        )

    def _open_connection(self) -> sqlite3.Connection:
        if self._db_path is not None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            target = str(self._db_path)
        else:
            target = ":memory:"
        conn = sqlite3.connect(target, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        if not self._is_memory:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _initialize_schema_and_seed(
        self,
        default_committee: list[dict[str, Any]],
        default_posts: list[dict[str, Any]],
        default_forms: list[dict[str, Any]],
    ) -> None:
        with self._lock:
            with self._conn:
                self._conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS sequences (
                        collection TEXT PRIMARY KEY,
                        next_id INTEGER NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS committee (
                        id INTEGER PRIMARY KEY,
                        full_name TEXT NOT NULL,
                        role TEXT NOT NULL,
                        responsibility_summary TEXT NOT NULL DEFAULT '',
                        email TEXT NOT NULL DEFAULT '',
                        phone TEXT NOT NULL DEFAULT '',
                        avatar_url TEXT NOT NULL DEFAULT '',
                        display_order INTEGER,
                        is_direct_contact INTEGER NOT NULL DEFAULT 0
                    );
                    CREATE TABLE IF NOT EXISTS posts (
                        id INTEGER PRIMARY KEY,
                        title TEXT NOT NULL,
                        summary TEXT NOT NULL,
                        category TEXT NOT NULL,
                        published_at TEXT NOT NULL DEFAULT '',
                        event_date TEXT NOT NULL DEFAULT '',
                        image_url TEXT NOT NULL DEFAULT '',
                        display_order INTEGER NULL
                    );
                    CREATE TABLE IF NOT EXISTS media_links (
                        id INTEGER PRIMARY KEY,
                        post_id INTEGER NULL REFERENCES posts(id) ON DELETE CASCADE,
                        media_type TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        canonical_url TEXT NOT NULL,
                        embed_url TEXT NOT NULL,
                        original_url TEXT NOT NULL DEFAULT '',
                        render_mode TEXT NOT NULL DEFAULT 'iframe',
                        aspect_width INTEGER NULL,
                        aspect_height INTEGER NULL,
                        hosted_externally INTEGER NOT NULL DEFAULT 1,
                        title TEXT NOT NULL DEFAULT ''
                    );
                    CREATE INDEX IF NOT EXISTS idx_media_links_post_id
                        ON media_links(post_id);
                    CREATE TABLE IF NOT EXISTS forms (
                        id INTEGER PRIMARY KEY,
                        form_type TEXT NOT NULL,
                        title TEXT NOT NULL,
                        description TEXT NOT NULL DEFAULT '',
                        canonical_url TEXT NOT NULL,
                        embed_url TEXT NOT NULL,
                        provider TEXT NOT NULL DEFAULT 'google_forms',
                        form_id TEXT NOT NULL DEFAULT '',
                        active INTEGER NOT NULL DEFAULT 1,
                        display_order INTEGER
                    );
                    """
                )
                committee_cols = {
                    r["name"]
                    for r in self._conn.execute("PRAGMA table_info(committee)")
                }
                if "is_direct_contact" not in committee_cols:
                    self._conn.execute(
                        "ALTER TABLE committee ADD COLUMN "
                        "is_direct_contact INTEGER NOT NULL DEFAULT 0"
                    )
                    self._conn.execute(
                        "UPDATE committee SET is_direct_contact = 1 "
                        "WHERE full_name = ?",
                        ("طه علي اغباريه",),
                    )
                media_cols = {
                    r["name"]
                    for r in self._conn.execute("PRAGMA table_info(media_links)")
                }
                if "render_mode" not in media_cols:
                    self._conn.execute(
                        "ALTER TABLE media_links ADD COLUMN "
                        "render_mode TEXT NOT NULL DEFAULT 'iframe'"
                    )
                if "aspect_width" not in media_cols:
                    self._conn.execute(
                        "ALTER TABLE media_links ADD COLUMN "
                        "aspect_width INTEGER NULL"
                    )
                if "aspect_height" not in media_cols:
                    self._conn.execute(
                        "ALTER TABLE media_links ADD COLUMN "
                        "aspect_height INTEGER NULL"
                    )
                post_cols = {
                    r["name"]
                    for r in self._conn.execute("PRAGMA table_info(posts)")
                }
                if "display_order" not in post_cols:
                    self._conn.execute(
                        "ALTER TABLE posts ADD COLUMN display_order INTEGER NULL"
                    )
                row = self._conn.execute(
                    "SELECT value FROM metadata WHERE key = 'seeded'"
                ).fetchone()
                if row is not None:
                    return

                temp_seed = CMSStore(
                    default_committee,
                    default_posts,
                    default_forms,
                    data_file=None,
                ).export_snapshot()
                self._write_snapshot_unlocked(temp_seed)

    def _write_snapshot_unlocked(self, snapshot: dict[str, Any]) -> None:
        self._conn.execute("DELETE FROM media_links")
        self._conn.execute("DELETE FROM posts")
        self._conn.execute("DELETE FROM committee")
        self._conn.execute("DELETE FROM forms")
        self._conn.execute("DELETE FROM sequences")

        committee = snapshot.get("committee", [])
        for member in committee:
            self._conn.execute(
                """
                INSERT INTO committee (
                    id, full_name, role, responsibility_summary,
                    email, phone, avatar_url, display_order, is_direct_contact
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(member["id"]),
                    member.get("fullName", ""),
                    member.get("role", ""),
                    member.get("responsibilitySummary", ""),
                    member.get("email", ""),
                    member.get("phone", ""),
                    member.get("avatarUrl", ""),
                    member.get("displayOrder"),
                    1 if member.get("isDirectContact") else 0,
                ),
            )

        posts = snapshot.get("posts", [])
        for post in posts:
            self._conn.execute(
                """
                INSERT INTO posts (
                    id, title, summary, category, published_at, event_date, image_url, display_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(post["id"]),
                    post.get("title", ""),
                    post.get("summary", ""),
                    post.get("category", "general"),
                    post.get("publishedAt", ""),
                    post.get("eventDate", ""),
                    post.get("imageUrl", ""),
                    post.get("displayOrder"),
                ),
            )

        media_links = snapshot.get("media_links", [])
        for link in media_links:
            self._conn.execute(
                """
                INSERT INTO media_links (
                    id, post_id, media_type, provider, canonical_url,
                    embed_url, original_url, render_mode, aspect_width, aspect_height,
                    hosted_externally, title
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(link["id"]),
                    link.get("postId"),
                    link.get("mediaType", "video"),
                    link.get("provider", ""),
                    link.get("canonicalUrl", ""),
                    link.get("embedUrl", ""),
                    link.get("originalUrl", ""),
                    link.get("renderMode", "iframe"),
                    link.get("aspectWidth"),
                    link.get("aspectHeight"),
                    1 if link.get("hostedExternally", True) else 0,
                    link.get("title", ""),
                ),
            )

        forms = snapshot.get("forms", [])
        for form in forms:
            self._conn.execute(
                """
                INSERT INTO forms (
                    id, form_type, title, description, canonical_url,
                    embed_url, provider, form_id, active, display_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(form["id"]),
                    form.get("formType", "feedback"),
                    form.get("title", ""),
                    form.get("description", ""),
                    form.get("canonicalUrl", ""),
                    form.get("embedUrl", ""),
                    form.get("provider", "google_forms"),
                    form.get("formId", ""),
                    1 if form.get("active", True) else 0,
                    form.get("displayOrder"),
                ),
            )

        next_ids = snapshot.get("next_ids", {})
        defaults = {
            "committee": max((int(r["id"]) for r in committee), default=0) + 1,
            "posts": max((int(r["id"]) for r in posts), default=0) + 1,
            "media_links": max((int(r["id"]) for r in media_links), default=0) + 1,
            "forms": max((int(r["id"]) for r in forms), default=0) + 1,
        }
        for collection, fallback in defaults.items():
            next_val = int(next_ids.get(collection) or fallback)
            self._conn.execute(
                "INSERT INTO sequences (collection, next_id) VALUES (?, ?)",
                (collection, max(next_val, fallback)),
            )

        self._conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('seeded', '1')"
        )

    def _allocate_id(self, collection: str) -> int:
        row = self._conn.execute(
            "SELECT next_id FROM sequences WHERE collection = ?",
            (collection,),
        ).fetchone()
        if row is None:
            next_id = 1
            self._conn.execute(
                "INSERT INTO sequences (collection, next_id) VALUES (?, ?)",
                (collection, 2),
            )
            return next_id
        allocated = int(row["next_id"])
        self._conn.execute(
            "UPDATE sequences SET next_id = ? WHERE collection = ?",
            (allocated + 1, collection),
        )
        return allocated

    @staticmethod
    def _row_to_committee(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "fullName": row["full_name"],
            "role": row["role"],
            "responsibilitySummary": row["responsibility_summary"],
            "email": row["email"],
            "phone": row["phone"],
            "avatarUrl": row["avatar_url"],
            "displayOrder": row["display_order"],
            "isDirectContact": bool(row["is_direct_contact"]),
        }

    @staticmethod
    def _row_to_media_link(row: sqlite3.Row) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": row["id"],
            "postId": row["post_id"],
            "mediaType": row["media_type"],
            "provider": row["provider"],
            "canonicalUrl": row["canonical_url"],
            "embedUrl": row["embed_url"],
            "originalUrl": row["original_url"],
            "renderMode": row["render_mode"],
            "hostedExternally": bool(row["hosted_externally"]),
            "title": row["title"],
        }
        if row["aspect_width"] is not None:
            result["aspectWidth"] = row["aspect_width"]
        if row["aspect_height"] is not None:
            result["aspectHeight"] = row["aspect_height"]
        return result

    @staticmethod
    def _row_to_post(
        row: sqlite3.Row, media_links: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            "id": row["id"],
            "title": row["title"],
            "summary": row["summary"],
            "category": row["category"],
            "publishedAt": row["published_at"],
            "eventDate": row["event_date"],
            "imageUrl": row["image_url"],
            "displayOrder": row["display_order"],
            "mediaLinks": media_links,
        }

    @staticmethod
    def _row_to_form(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "formType": row["form_type"],
            "title": row["title"],
            "description": row["description"],
            "canonicalUrl": row["canonical_url"],
            "embedUrl": row["embed_url"],
            "provider": row["provider"],
            "formId": row["form_id"],
            "active": bool(row["active"]),
            "displayOrder": row["display_order"],
        }

    def _replace_post_media_links_unlocked(
        self, post_id: int, links: list[dict[str, Any]]
    ) -> None:
        self._conn.execute("DELETE FROM media_links WHERE post_id = ?", (post_id,))
        for link in links:
            link_id = self._allocate_id("media_links")
            self._conn.execute(
                """
                INSERT INTO media_links (
                    id, post_id, media_type, provider, canonical_url,
                    embed_url, original_url, render_mode, aspect_width, aspect_height,
                    hosted_externally, title
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    link_id,
                    post_id,
                    link.get("mediaType", "video"),
                    link.get("provider", ""),
                    link.get("canonicalUrl", ""),
                    link.get("embedUrl", ""),
                    link.get("originalUrl", ""),
                    link.get("renderMode", "iframe"),
                    link.get("aspectWidth"),
                    link.get("aspectHeight"),
                    1 if link.get("hostedExternally", True) else 0,
                    link.get("title", ""),
                ),
            )

    def _hydrate_post_unlocked(self, post_row: sqlite3.Row) -> dict[str, Any]:
        link_rows = self._conn.execute(
            "SELECT * FROM media_links WHERE post_id = ? ORDER BY id ASC",
            (post_row["id"],),
        ).fetchall()
        links = [self._row_to_media_link(r) for r in link_rows]
        return self._row_to_post(post_row, links)

    # --- Committee CRUD ---

    def list_committee(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM committee ORDER BY id ASC"
            ).fetchall()
            return [self._row_to_committee(r) for r in rows]

    def get_committee_member(self, member_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM committee WHERE id = ?", (member_id,)
            ).fetchone()
            return self._row_to_committee(row) if row is not None else None

    def create_committee_member(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            with self._conn:
                display_order = record.get("displayOrder")
                if display_order is None:
                    row = self._conn.execute(
                        "SELECT MAX(display_order) AS max_order, COUNT(*) AS cnt FROM committee"
                    ).fetchone()
                    max_order = int(row["max_order"] or 0) if row is not None else 0
                    cnt = int(row["cnt"] or 0) if row is not None else 0
                    display_order = max(max_order, cnt) + 1
                member_id = self._allocate_id("committee")
                self._conn.execute(
                    """
                    INSERT INTO committee (
                        id, full_name, role, responsibility_summary,
                        email, phone, avatar_url, display_order, is_direct_contact
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        member_id,
                        record.get("fullName", ""),
                        record.get("role", ""),
                        record.get("responsibilitySummary", ""),
                        record.get("email", ""),
                        record.get("phone", ""),
                        record.get("avatarUrl", ""),
                        display_order,
                        1 if record.get("isDirectContact") else 0,
                    ),
                )
            return self.get_committee_member(member_id)  # type: ignore[return-value]

    def update_committee_member(
        self, member_id: int, updates: dict[str, Any]
    ) -> dict[str, Any] | None:
        with self._lock:
            existing = self.get_committee_member(member_id)
            if existing is None:
                return None
            merged = {**existing, **copy.deepcopy(updates)}
            with self._conn:
                self._conn.execute(
                    """
                    UPDATE committee
                    SET full_name = ?, role = ?, responsibility_summary = ?,
                        email = ?, phone = ?, avatar_url = ?, display_order = ?,
                        is_direct_contact = ?
                    WHERE id = ?
                    """,
                    (
                        merged.get("fullName", ""),
                        merged.get("role", ""),
                        merged.get("responsibilitySummary", ""),
                        merged.get("email", ""),
                        merged.get("phone", ""),
                        merged.get("avatarUrl", ""),
                        merged.get("displayOrder"),
                        1 if merged.get("isDirectContact") else 0,
                        member_id,
                    ),
                )
            return self.get_committee_member(member_id)

    def delete_committee_member(self, member_id: int) -> bool:
        with self._lock:
            with self._conn:
                cur = self._conn.execute(
                    "DELETE FROM committee WHERE id = ?", (member_id,)
                )
                return cur.rowcount > 0

    def reorder_committee(self, ordered_ids: list[int]) -> list[dict[str, Any]] | None:
        with self._lock:
            existing_rows = self._conn.execute(
                "SELECT id FROM committee ORDER BY COALESCE(display_order, 9999) ASC, id ASC"
            ).fetchall()
            existing_ids = [int(row["id"]) for row in existing_rows]
            existing_set = set(existing_ids)
            for mid in ordered_ids:
                if int(mid) not in existing_set:
                    return None
            normalized_ids = [int(mid) for mid in ordered_ids]
            seen = set(normalized_ids)
            full_ids = normalized_ids + [
                mid for mid in existing_ids if mid not in seen
            ]
            with self._conn:
                for order_idx, mid in enumerate(full_ids, start=1):
                    self._conn.execute(
                        "UPDATE committee SET display_order = ? WHERE id = ?",
                        (order_idx, mid),
                    )
            return self.list_committee()

    # --- Posts CRUD ---

    def list_posts(self) -> list[dict[str, Any]]:
        with self._lock:
            post_rows = self._conn.execute(
                "SELECT * FROM posts ORDER BY id ASC"
            ).fetchall()
            link_rows = self._conn.execute(
                "SELECT * FROM media_links WHERE post_id IS NOT NULL ORDER BY id ASC"
            ).fetchall()
            links_by_post: dict[int, list[dict[str, Any]]] = {}
            for link_row in link_rows:
                pid = int(link_row["post_id"])
                links_by_post.setdefault(pid, []).append(
                    self._row_to_media_link(link_row)
                )
            return [
                self._row_to_post(row, links_by_post.get(int(row["id"]), []))
                for row in post_rows
            ]

    def get_post(self, post_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM posts WHERE id = ?", (post_id,)
            ).fetchone()
            if row is None:
                return None
            return self._hydrate_post_unlocked(row)

    def create_post(
        self, record: dict[str, Any], media_links: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        with self._lock:
            with self._conn:
                display_order = record.get("displayOrder")
                if display_order is None:
                    has_ordered = self._conn.execute(
                        "SELECT 1 FROM posts WHERE display_order IS NOT NULL LIMIT 1"
                    ).fetchone()
                    if has_ordered is not None:
                        self._conn.execute(
                            "UPDATE posts SET display_order = display_order + 1 WHERE display_order IS NOT NULL"
                        )
                        display_order = 1
                post_id = self._allocate_id("posts")
                self._conn.execute(
                    """
                    INSERT INTO posts (
                        id, title, summary, category, published_at, event_date, image_url, display_order
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        post_id,
                        record.get("title", ""),
                        record.get("summary", ""),
                        record.get("category", "general"),
                        record.get("publishedAt", ""),
                        record.get("eventDate", ""),
                        record.get("imageUrl", ""),
                        display_order,
                    ),
                )
                if media_links:
                    self._replace_post_media_links_unlocked(post_id, media_links)
            return self.get_post(post_id)  # type: ignore[return-value]

    def update_post(
        self,
        post_id: int,
        updates: dict[str, Any],
        media_links: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            existing = self.get_post(post_id)
            if existing is None:
                return None
            clean_updates = copy.deepcopy(updates)
            clean_updates.pop("mediaLinks", None)
            merged = {**existing, **clean_updates}
            with self._conn:
                self._conn.execute(
                    """
                    UPDATE posts
                    SET title = ?, summary = ?, category = ?,
                        published_at = ?, event_date = ?, image_url = ?, display_order = ?
                    WHERE id = ?
                    """,
                    (
                        merged.get("title", ""),
                        merged.get("summary", ""),
                        merged.get("category", "general"),
                        merged.get("publishedAt", ""),
                        merged.get("eventDate", ""),
                        merged.get("imageUrl", ""),
                        merged.get("displayOrder"),
                        post_id,
                    ),
                )
                if media_links is not None:
                    self._replace_post_media_links_unlocked(post_id, media_links)
            return self.get_post(post_id)

    def delete_post(self, post_id: int) -> bool:
        with self._lock:
            with self._conn:
                cur = self._conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
                return cur.rowcount > 0

    def reorder_posts(self, ordered_ids: list[int]) -> list[dict[str, Any]] | None:
        with self._lock:
            existing_rows = self._conn.execute(
                "SELECT id FROM posts ORDER BY id ASC"
            ).fetchall()
            existing_ids = [int(row["id"]) for row in existing_rows]
            existing_set = set(existing_ids)
            for pid in ordered_ids:
                if int(pid) not in existing_set:
                    return None
            normalized_ids = [int(pid) for pid in ordered_ids]
            seen = set(normalized_ids)
            full_ids = normalized_ids + [
                pid for pid in existing_ids if pid not in seen
            ]
            with self._conn:
                for order_idx, pid in enumerate(full_ids, start=1):
                    self._conn.execute(
                        "UPDATE posts SET display_order = ? WHERE id = ?",
                        (order_idx, pid),
                    )
            return self.list_posts()

    # --- Media Links CRUD ---

    def list_media_links(self, post_id: int | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if post_id is None:
                rows = self._conn.execute(
                    "SELECT * FROM media_links ORDER BY id ASC"
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM media_links WHERE post_id = ? ORDER BY id ASC",
                    (post_id,),
                ).fetchall()
            return [self._row_to_media_link(r) for r in rows]

    def get_media_link(self, link_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM media_links WHERE id = ?", (link_id,)
            ).fetchone()
            return self._row_to_media_link(row) if row is not None else None

    def create_media_link(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            with self._conn:
                link_id = self._allocate_id("media_links")
                self._conn.execute(
                    """
                    INSERT INTO media_links (
                        id, post_id, media_type, provider, canonical_url,
                        embed_url, original_url, render_mode, aspect_width, aspect_height,
                        hosted_externally, title
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        link_id,
                        record.get("postId"),
                        record.get("mediaType", "video"),
                        record.get("provider", ""),
                        record.get("canonicalUrl", ""),
                        record.get("embedUrl", ""),
                        record.get("originalUrl", ""),
                        record.get("renderMode", "iframe"),
                        record.get("aspectWidth"),
                        record.get("aspectHeight"),
                        1 if record.get("hostedExternally", True) else 0,
                        record.get("title", ""),
                    ),
                )
            return self.get_media_link(link_id)  # type: ignore[return-value]

    def update_media_link(
        self, link_id: int, updates: dict[str, Any]
    ) -> dict[str, Any] | None:
        with self._lock:
            existing = self.get_media_link(link_id)
            if existing is None:
                return None
            merged = {**existing, **copy.deepcopy(updates)}
            with self._conn:
                self._conn.execute(
                    """
                    UPDATE media_links
                    SET post_id = ?, media_type = ?, provider = ?, canonical_url = ?,
                        embed_url = ?, original_url = ?, render_mode = ?,
                        aspect_width = ?, aspect_height = ?,
                        hosted_externally = ?, title = ?
                    WHERE id = ?
                    """,
                    (
                        merged.get("postId"),
                        merged.get("mediaType", "video"),
                        merged.get("provider", ""),
                        merged.get("canonicalUrl", ""),
                        merged.get("embedUrl", ""),
                        merged.get("originalUrl", ""),
                        merged.get("renderMode", "iframe"),
                        merged.get("aspectWidth"),
                        merged.get("aspectHeight"),
                        1 if merged.get("hostedExternally", True) else 0,
                        merged.get("title", ""),
                        link_id,
                    ),
                )
            return self.get_media_link(link_id)

    def delete_media_link(self, link_id: int) -> bool:
        with self._lock:
            with self._conn:
                cur = self._conn.execute(
                    "DELETE FROM media_links WHERE id = ?", (link_id,)
                )
                return cur.rowcount > 0

    # --- Google Forms CRUD ---

    def list_forms(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM forms
                ORDER BY COALESCE(display_order, 9999) ASC, id ASC
                """
            ).fetchall()
            return [self._row_to_form(r) for r in rows]

    def get_form(self, form_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM forms WHERE id = ?", (form_id,)
            ).fetchone()
            return self._row_to_form(row) if row is not None else None

    def create_form(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            with self._conn:
                display_order = record.get("displayOrder")
                if display_order is None:
                    self._conn.execute(
                        "UPDATE forms SET display_order = display_order + 1 WHERE display_order IS NOT NULL"
                    )
                    display_order = 1
                form_id = self._allocate_id("forms")
                self._conn.execute(
                    """
                    INSERT INTO forms (
                        id, form_type, title, description, canonical_url,
                        embed_url, provider, form_id, active, display_order
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        form_id,
                        record.get("formType", "feedback"),
                        record.get("title", ""),
                        record.get("description", ""),
                        record.get("canonicalUrl", ""),
                        record.get("embedUrl", ""),
                        record.get("provider", "google_forms"),
                        record.get("formId", ""),
                        1 if record.get("active", True) else 0,
                        display_order,
                    ),
                )
            return self.get_form(form_id)  # type: ignore[return-value]

    def update_form(
        self, form_id: int, updates: dict[str, Any]
    ) -> dict[str, Any] | None:
        with self._lock:
            existing = self.get_form(form_id)
            if existing is None:
                return None
            merged = {**existing, **copy.deepcopy(updates)}
            with self._conn:
                self._conn.execute(
                    """
                    UPDATE forms
                    SET form_type = ?, title = ?, description = ?, canonical_url = ?,
                        embed_url = ?, provider = ?, form_id = ?, active = ?, display_order = ?
                    WHERE id = ?
                    """,
                    (
                        merged.get("formType", "feedback"),
                        merged.get("title", ""),
                        merged.get("description", ""),
                        merged.get("canonicalUrl", ""),
                        merged.get("embedUrl", ""),
                        merged.get("provider", "google_forms"),
                        merged.get("formId", ""),
                        1 if merged.get("active", True) else 0,
                        merged.get("displayOrder"),
                        form_id,
                    ),
                )
            return self.get_form(form_id)

    def delete_form(self, form_id: int) -> bool:
        with self._lock:
            with self._conn:
                cur = self._conn.execute(
                    "DELETE FROM forms WHERE id = ?", (form_id,)
                )
                return cur.rowcount > 0

    def reorder_forms(self, ordered_ids: list[int]) -> list[dict[str, Any]] | None:
        with self._lock:
            existing_rows = self._conn.execute(
                "SELECT id FROM forms ORDER BY COALESCE(display_order, 9999) ASC, id ASC"
            ).fetchall()
            existing_ids = [int(row["id"]) for row in existing_rows]
            existing_set = set(existing_ids)
            for fid in ordered_ids:
                if int(fid) not in existing_set:
                    return None
            normalized_ids = [int(fid) for fid in ordered_ids]
            seen = set(normalized_ids)
            full_ids = normalized_ids + [
                fid for fid in existing_ids if fid not in seen
            ]
            with self._conn:
                for order_idx, fid in enumerate(full_ids, start=1):
                    self._conn.execute(
                        "UPDATE forms SET display_order = ? WHERE id = ?",
                        (order_idx, fid),
                    )
            return self.list_forms()

    def export_snapshot(self) -> dict[str, Any]:
        """Return a deep-copied JSON-compatible snapshot of all collections and sequence counters."""
        with self._lock:
            posts = [
                {k: v for k, v in p.items() if k != "mediaLinks"}
                for p in self.list_posts()
            ]
            seq_rows = self._conn.execute(
                "SELECT collection, next_id FROM sequences"
            ).fetchall()
            next_ids = {row["collection"]: int(row["next_id"]) for row in seq_rows}
            return {
                "committee": self.list_committee(),
                "posts": posts,
                "media_links": self.list_media_links(),
                "forms": self.list_forms(),
                "next_ids": next_ids,
            }

    def storage_info(self) -> dict[str, Any]:
        """Return non-secret storage diagnostics for health/readiness reporting."""
        with self._lock:
            size_bytes = 0
            if self._db_path is not None:
                if self._db_path.is_file():
                    size_bytes += self._db_path.stat().st_size
                for suffix in ("-wal", "-shm"):
                    sidecar = Path(f"{self._db_path}{suffix}")
                    if sidecar.is_file():
                        size_bytes += sidecar.stat().st_size

            counts = {
                "committee": int(
                    self._conn.execute("SELECT COUNT(*) FROM committee").fetchone()[0]
                ),
                "posts": int(
                    self._conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
                ),
                "mediaLinks": int(
                    self._conn.execute("SELECT COUNT(*) FROM media_links").fetchone()[0]
                ),
                "forms": int(
                    self._conn.execute("SELECT COUNT(*) FROM forms").fetchone()[0]
                ),
            }
            return {
                "backend": "sqlite",
                "persisted": not self._is_memory,
                "sizeBytes": int(size_bytes),
                "counts": counts,
            }


def _parse_sqlite_database_url(database_url: str) -> str:
    raw = database_url.strip()
    if raw == "sqlite:///:memory:":
        return ":memory:"
    parsed = urlsplit(raw)
    if parsed.scheme.lower() != "sqlite":
        raise ValueError(
            f"Unsupported database URL scheme '{parsed.scheme}'. Only sqlite:/// URLs are supported."
        )
    if parsed.netloc and parsed.netloc not in ("", "localhost"):
        raise ValueError("Remote host is not supported in sqlite:/// URLs.")
    path = unquote(parsed.path or "")
    if raw.startswith("sqlite:////"):
        return path
    if raw.startswith("sqlite:///"):
        # Relative path after sqlite:///
        return path.lstrip("/") if not path.startswith("//") else path
    if path in ("/:memory:", ":memory:", ""):
        return ":memory:"
    return path


def create_cms_store(
    default_committee: list[dict[str, Any]],
    default_posts: list[dict[str, Any]],
    default_forms: list[dict[str, Any]] | None = None,
    *,
    data_file: str | Path | None = None,
    storage_backend: str = "auto",
    database_url: str | None = None,
) -> CMSStore | SQLiteCMSStore:
    """Instantiate either CMSStore (JSON) or SQLiteCMSStore based on free-tier config."""
    backend = (storage_backend or "auto").strip().lower()
    if backend not in ("auto", "json", "sqlite"):
        raise ValueError(
            f"Unsupported storage backend '{storage_backend}'. Allowed: auto, json, sqlite."
        )

    cleaned_url = (database_url or "").strip()
    if cleaned_url:
        sqlite_target = _parse_sqlite_database_url(cleaned_url)
        if backend == "json":
            raise ValueError("Cannot use sqlite DATABASE_URL with storage_backend='json'.")
        return SQLiteCMSStore(
            default_committee,
            default_posts,
            default_forms,
            db_path=sqlite_target,
        )

    if backend == "sqlite":
        target: str | Path = data_file if data_file else ":memory:"
        return SQLiteCMSStore(
            default_committee,
            default_posts,
            default_forms,
            db_path=target,
        )

    if backend == "auto" and data_file is not None:
        ext = Path(str(data_file)).suffix.lower()
        if ext in (".db", ".sqlite", ".sqlite3"):
            return SQLiteCMSStore(
                default_committee,
                default_posts,
                default_forms,
                db_path=data_file,
            )

    return CMSStore(
        default_committee,
        default_posts,
        default_forms,
        data_file=data_file,
    )


def migrate_json_to_sqlite(
    json_path: str | Path, sqlite_path: str | Path
) -> dict[str, int]:
    """Migrate an existing JSON CMSStore file into a SQLiteCMSStore database."""
    source_path = Path(json_path)
    if not source_path.is_file():
        raise FileNotFoundError(f"JSON CMS store file not found: {source_path}")

    json_store = CMSStore([], [], [], data_file=source_path)
    snapshot = json_store.export_snapshot()

    sqlite_store = SQLiteCMSStore([], [], [], db_path=sqlite_path)
    try:
        with sqlite_store._lock:
            with sqlite_store._conn:
                sqlite_store._write_snapshot_unlocked(snapshot)
        counts = sqlite_store.storage_info()["counts"]
    finally:
        sqlite_store.close()

    return counts
