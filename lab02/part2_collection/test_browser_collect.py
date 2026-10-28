"""仅测试阻断和CSV完整性；不请求网站、不写标准CSV、不连接数据库。"""
import argparse
import tempfile
import unittest
from pathlib import Path

import browser_collect as browser
import collect_houses as collector


class BrowserCollectorTests(unittest.TestCase):
    def test_verification_page_stops_before_any_record_is_saved(self):
        class VerificationDriver:
            current_url = collector.BASE_URL
            page_source = "<html><title>访问验证</title><body>请完成验证</body></html>"

        with self.assertRaises(collector.CollectionError) as result:
            browser.wait_for_houses(VerificationDriver(), collector.BASE_URL, 1)
        self.assertEqual(result.exception.kind, "blocked_source")

    def test_page_limit_cannot_exceed_eight(self):
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            browser.arguments(["--pages", "9"])

    def test_real_captured_records_roundtrip_without_changing_units(self):
        from bs4 import BeautifulSoup
        result_file = browser.BASE / "browser_last_run.json"
        if not result_file.is_file():
            self.skipTest("尚无独立脚本实际运行证据")
        result = collector.load_json(result_file)
        if result.get("state") != "ready":
            self.skipTest("最新实际运行未取得房源")
        html = Path(result["manifest_path"]).parent / "page_001.html"
        records = [collector.parse_record(row) for row in BeautifulSoup(html.read_text(encoding="utf-8"), "html.parser").select("div.property")]
        self.assertGreater(len(records), 0)
        with tempfile.TemporaryDirectory(prefix="csv_check_", dir=browser.BASE / "evidence") as folder:
            path, count = browser.write_run_csv(Path(folder), records + records[:1])
            self.assertEqual(count, len(set(records)))
            self.assertEqual(collector.read_csv_records(path), list(dict.fromkeys(records)))
            self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
