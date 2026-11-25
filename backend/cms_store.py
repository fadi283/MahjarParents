"""Thread-safe atomic JSON-backed CMS store for committee, posts, media links, and forms."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Any

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
