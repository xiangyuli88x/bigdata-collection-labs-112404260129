"""浏览器DOM快照入口安全测试。

不请求网络、不运行采集、不写标准CSV/status，不构造房源；测试HTML仅含明确的
完整性检查标记，property_count=0，不能通过真实房源页的parse_page检查。
"""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import collect_houses as collector


class BrowserSourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix=".browser-source-check-", dir=collector.PART_DIR)
        self.root = Path(self.temporary.name)
        self.sources = self.root / "sources"
        self.sources.mkdir()
        self.file = self.sources / "integrity_only.html"
        self.file.write_text("<!doctype html><html><title>Unit test integrity marker only</title><body>no property records</body></html>", encoding="utf-8")
        self.manifest = {"source": "browser_saved", "provider": "unit test fixture only",
                         "capture_method": "browser_dom_serialization", "captured_at": "2026-10-27T00:00:00+08:00",
                         "pages": [{"url": collector.BASE_URL, "file": self.file.name,
                                    "sha256": collector.sha256_file(self.file), "captured_at": "2026-10-27T00:00:00+08:00",
                                    "property_count": 0}]}
        self.path = self.sources / "manifest.json"
        self.run = type("RunFixture", (), {})()
        self.run.directory = self.root / "run"
        self.run.directory.mkdir()
        self.run.result = {"source_mode": "browser_snapshot"}
        self.part_patch = patch.object(collector, "PART_DIR", self.root)
        self.part_patch.start()
        self.net_patch = patch.object(collector.requests.Session, "get", side_effect=AssertionError("network forbidden in unit tests"))
        self.net_patch.start()

    def tearDown(self):
        self.net_patch.stop()
        self.part_patch.stop()
        self.temporary.cleanup()

    def source(self):
        self.path.write_text(json.dumps(self.manifest), encoding="utf-8")
        return collector.PageSource(self.run, browser_manifest=self.path)

    def test_browser_dom_is_separate_from_http_and_teacher_response(self):
        source = self.source()
        try:
            html, metadata = source.get(collector.BASE_URL, 1)
            self.assertEqual(metadata["source_mode"], "browser_snapshot")
            self.assertIsNone(metadata["status_code"])
            self.assertEqual(metadata["capture_method"], "browser_dom_serialization")
            self.assertIn("snapshot_path", metadata)
            self.assertNotIn("raw_path", metadata)
            self.assertNotIn("teacher_sha256", metadata)
            self.assertEqual(collector.verify_response(metadata), html)
            with self.assertRaises(collector.CollectionError):
                collector.parse_page(html)
        finally:
            source.close()

    def test_source_label_must_explicitly_be_browser_saved(self):
        self.manifest["source"] = "teacher_provided"
        with self.assertRaises(collector.CollectionError):
            self.source()

    def test_capture_method_and_time_are_required(self):
        for key in ("capture_method", "captured_at"):
            original = self.manifest.pop(key)
            with self.assertRaises(collector.CollectionError):
                self.source()
            self.manifest[key] = original

    def test_page_count_must_be_an_integer_not_boolean(self):
        self.manifest["pages"][0]["property_count"] = True
        with self.assertRaises(collector.CollectionError):
            self.source()

    def test_page_count_is_rechecked_against_dom(self):
        self.manifest["pages"][0]["property_count"] = 60
        source = self.source()
        try:
            with self.assertRaises(collector.CollectionError):
                source.get(collector.BASE_URL, 1)
        finally:
            source.close()

    def test_file_changes_after_initialization_are_rejected(self):
        source = self.source()
        try:
            self.file.write_text("mutated unit test marker", encoding="utf-8")
            with self.assertRaises(collector.CollectionError):
                source.get(collector.BASE_URL, 1)
        finally:
            source.close()

    def test_manifest_cannot_read_outside_its_directory(self):
        outside = self.root / "outside.html"
        outside.write_bytes(self.file.read_bytes())
        self.manifest["pages"][0]["file"] = "../outside.html"
        with self.assertRaises(collector.CollectionError):
            self.source()

    def test_saved_metadata_cannot_falsely_claim_http_200(self):
        source = self.source()
        try:
            _, metadata = source.get(collector.BASE_URL, 1)
            metadata["status_code"] = 200
            with self.assertRaises(collector.CollectionError):
                collector.verify_response(metadata)
        finally:
            source.close()

    def test_teacher_and_browser_cli_modes_are_mutually_exclusive(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                collector.main(["trial", "--offline-manifest", "unused", "--browser-manifest", "unused"])
        self.assertEqual(result.exception.code, 2)

    def test_mixed_mode_page_chain_is_rejected_before_parsing(self):
        pages = [{"response": {"source_mode": "browser_snapshot"}}]
        with self.assertRaisesRegex(collector.CollectionError, "模式"):
            collector.verify_pages(pages, source_mode="online")

    def test_same_address_http_to_https_upgrade_is_preserved_and_bounded(self):
        self.manifest["pages"][0]["requested_url"] = collector.BASE_URL
        self.manifest["pages"][0]["url"] = collector.BASE_URL.replace("http:", "https:")
        source = self.source()
        try:
            _, metadata = source.get(collector.BASE_URL, 1)
            self.assertEqual(metadata["requested_url"], collector.BASE_URL)
            self.assertEqual(metadata["url"], collector.BASE_URL.replace("http:", "https:"))
            collector.verify_response(metadata)
        finally:
            source.close()
        forbidden = [
            (collector.BASE_URL, "https://www.bspider.top/anjuke/?page=2"),
            (collector.BASE_URL.replace("http:", "https:"), collector.BASE_URL),
            (collector.BASE_URL, "https://www.bspider.top/anjuke/other/"),
            (collector.BASE_URL, "https://example.org/anjuke/"),
        ]
        for requested, actual in forbidden:
            with self.subTest(actual=actual):
                with self.assertRaises(collector.CollectionError):
                    collector.checked_browser_navigation(requested, actual)

    def test_explicit_eight_page_scope_does_not_claim_site_completion(self):
        manifest = {"complete": False, "scope_complete": True, "pages": [None] * 8,
                    "collection_scope": {"type": "first_pages", "page_limit": 8, "user_requested": True}}
        self.assertTrue(collector.is_first_pages_scope(manifest))
        self.assertFalse(manifest["complete"])
        for change in ({"complete": True}, {"scope_complete": False}, {"pages": [None] * 7},
                       {"collection_scope": {"type": "first_pages", "page_limit": 8, "user_requested": False}}):
            with self.subTest(change=change):
                with self.assertRaises(collector.CollectionError):
                    collector.is_first_pages_scope({**manifest, **change})

    def test_incomplete_site_without_explicit_scope_is_not_a_limited_collection(self):
        self.assertFalse(collector.is_first_pages_scope({"complete": False, "pages": [None] * 8}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
