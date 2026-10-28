"""第二阶段的安全检查；不构造房源、不请求网络、不写标准 CSV。

运行前先完成一次真实 trial，--response 指向本次保存的真实响应 HTML。
这些检查只证明边界和验证页处理，不能证明真实房源解析、翻页或 CSV 已完成。
"""

import argparse
import hashlib
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
import os

import collect_houses as collector


def main(argv=None):
    if argv is None and "ipykernel" in sys.modules:
        argv = []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--response", type=Path, required=True)
    args = parser.parse_args(argv)
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "passed": bool(ok), "detail": detail})
        if not ok:
            raise AssertionError(name + ": " + detail)

    check("固定8字段顺序", collector.FIELDS == (
        "title", "house", "address", "struct", "area", "floor", "maketime", "price"))
    expected = "http://www.bspider.top/anjuke/?page=2"
    check("href 通过 urljoin 补全", collector.checked_url("?page=2") == expected)
    blocked_urls = [
        "https://www.anjuke.com/", "//example.org/anjuke/", "/other/",
        "file:///tmp/a", "javascript:void(0)", "http://www.bspider.top.evil/anjuke/",
        "http://student@www.bspider.top/anjuke/", "http://www.bspider.top:9999/anjuke/",
        "http://www.bspider.top/anjuke/../other/", "http://www.bspider.top/anjuke/%2e%2e/other/",
    ]
    for href in blocked_urls:
        try:
            collector.checked_url(href)
        except collector.CollectionError:
            check("拒绝越站或异常链接", True, href)
        else:
            check("拒绝越站或异常链接", False, href)

    check("真实响应文件存在", args.response.is_file(), str(args.response))
    actual_html = args.response.read_text(encoding="utf-8-sig")
    metadata_path = args.response.with_suffix(".json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    check("原始响应与解码页面哈希及内容一致", collector.verify_response(metadata) == actual_html)
    try:
        collector.parse_page(actual_html)
    except collector.CollectionError as exc:
        check("真实访问验证页立即停止", exc.kind == "blocked_source", str(exc))
    else:
        check("真实访问验证页立即停止", False, "当前文件不是验证页；此项需改做真实房源核验")

    with redirect_stdout(io.StringIO()):
        help_code = collector.main([])
    check("Notebook main([]) 不读取 kernel -f", help_code in (None, 0))
    source_hash = collector.sha256_file(Path(collector.__file__))
    check("文件 SHA256 可复核", source_hash == hashlib.sha256(Path(collector.__file__).read_bytes()).hexdigest())

    # 仅用无房源含义的标记文字检查保护，不创建标准 CSV，不调用采集/写入函数。
    original_csv, original_part = collector.CSV_PATH, collector.PART_DIR
    with TemporaryDirectory(prefix=".protection-check-", dir=original_part) as temporary:
        protected_file = Path(temporary) / "unknown_source.txt"
        sentinel = b"existing opaque user file; protection check only\n"
        protected_file.write_bytes(sentinel)
        try:
            collector.CSV_PATH, collector.PART_DIR = protected_file, Path(temporary)
            try:
                collector.verify_csv_bundle()
            except collector.CollectionError as exc:
                check("不明来源文件拒绝作为采集CSV", "来源" in str(exc), str(exc))
            else:
                check("不明来源文件拒绝作为采集CSV", False)
            check("不明来源文件保持字节不变", protected_file.read_bytes() == sentinel)
        finally:
            collector.CSV_PATH, collector.PART_DIR = original_csv, original_part

    # 检查实际阻断状态，不创建 CSV 也不改变来源状态。
    part_dir = Path(__file__).resolve().parent
    status = json.loads((part_dir / "status.json").read_text(encoding="utf-8"))
    required = {"stage", "state", "checked_at", "source_mode", "csv_path", "csv_sha256",
                "raw_count", "deduplicated_count", "pages", "complete", "reason"}
    check("状态协议字段完整", required <= status.keys())
    check("来源受阻未误标 ready", status["stage"] == 2 and status["state"] == "blocked_source"
          and status["complete"] is False)
    check("无来源时CSV路径和hash为空", status["csv_path"] is None and status["csv_sha256"] is None)
    check("无真实房源时数量为零", status["raw_count"] == 0 and status["deduplicated_count"] == 0)
    check("未生成标准CSV", not (part_dir.parent / "data" / "houseinfo.csv").exists())

    report = {"checked_at": collector.now(), "checks": checks,
              "passed": len(checks), "failed": 0,
              "response": str(args.response.resolve()),
              "response_sha256": hashlib.sha256(args.response.read_bytes()).hexdigest(),
              "scope": "代码边界与真实验证页识别；不含真实房源字段、在线翻页或CSV业务验收"}
    output = part_dir / "evidence" / "safety_checks.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, delete=False) as temp:
        json.dump(report, temp, ensure_ascii=False, indent=2)
        temp.write("\n")
        temp.flush()
        os.fsync(temp.fileno())
        temporary = Path(temp.name)
    os.replace(temporary, output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
