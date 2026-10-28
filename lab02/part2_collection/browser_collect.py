"""独立浏览器采集：Selenium打开教学站 → 沿下一页链接 → 保存真实HTML和CSV。

在课程Jupyter终端运行（不依赖Codex浏览器工具）：
    python part2_collection/browser_collect.py

默认最多8页。每次结果保存在本目录 evidence/runs/browser_日期时间_编号/，
不替换已有标准CSV，不连接MySQL。遇到验证页、重复页面或缺失字段立即停止。
"""
import argparse
import csv
import io
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

try:
    from . import collect_houses as collector
except ImportError:
    import collect_houses as collector

BASE = Path(__file__).resolve().parent


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pages", type=int, choices=range(1, 9), default=8, metavar="1-8")
    parser.add_argument("--timeout", type=float, default=25, help="单页等待秒数，默认25")
    parser.add_argument("--delay", type=float, default=1, help="两页间隔秒数，至少1秒")
    parser.add_argument("--headed", action="store_true", help="显示浏览器窗口；需要桌面环境")
    parser.add_argument("--headless", action="store_true", help="不显示窗口；课程容器自动使用此模式")
    parser.add_argument("--browser-binary", type=Path, help="可选Chrome/Chromium程序路径")
    parser.add_argument("--driver-path", type=Path, help="可选chromedriver路径；默认Selenium Manager管理")
    args = parser.parse_args(argv)
    if args.timeout <= 0 or args.delay < 1:
        parser.error("timeout必须大于0，delay必须至少1秒")
    if args.headed and args.headless:
        parser.error("--headed与--headless不能同时使用")
    return args


def create_driver(args):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    options = Options()
    options.page_load_strategy = "eager"
    binary = args.browser_binary
    if binary is None and os.name != "nt":
        candidates = sorted(Path("/ms-playwright").glob("chromium-*/chrome-linux64/chrome"))
        binary = candidates[-1] if candidates else None
    if binary is not None:
        if not binary.is_file():
            raise FileNotFoundError(f"浏览器程序不存在：{binary}")
        options.binary_location = str(binary)
    headless = args.headless or (os.name != "nt" and not os.environ.get("DISPLAY") and not args.headed)
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,1000")
    if Path("/.dockerenv").exists():
        # 复用课程Notebook已采用的容器启动参数，不改变主机Chrome设置。
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
    service = Service(executable_path=str(args.driver_path)) if args.driver_path else Service()
    driver = webdriver.Chrome(service=service, options=options)
    try:
        driver.set_page_load_timeout(args.timeout)
        return driver
    except Exception:
        driver.quit()
        raise


def wait_for_houses(driver, requested_url, timeout):
    """等待真实字段完整；验证页立即报错，不尝试绕过验证。"""
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.support.ui import WebDriverWait
    last_error = None

    def ready(browser):
        nonlocal last_error
        actual_url = browser.current_url
        collector.checked_browser_navigation(requested_url, actual_url)
        html = browser.page_source
        try:
            soup = collector.parse_page(html, actual_url)
            records = [collector.parse_record(row) for row in soup.select("div.property")]
            following, button = collector.next_page(soup, actual_url)
            return html, actual_url, records, following, button
        except collector.CollectionError as exc:
            if exc.kind == "blocked_source":
                raise
            last_error = exc
            return False

    try:
        return WebDriverWait(driver, timeout, poll_frequency=0.5).until(ready)
    except TimeoutException as exc:
        raise collector.CollectionError(f"等待房源字段或分页结构超时：{last_error or '页面尚未就绪'}") from exc


def capture_pages(driver, args, folder, emit, manifest):
    requested_url = collector.BASE_URL
    seen_urls, seen_fingerprints = set(), set()
    all_records = []
    for number in range(1, args.pages + 1):
        from selenium.common.exceptions import TimeoutException
        try:
            driver.get(requested_url)  # 正常浏览器导航，不使用requests或隐藏接口。
        except TimeoutException:
            emit("navigation_timeout", page=number, requested_url=requested_url)
        html, actual_url, records, following, button = wait_for_houses(driver, requested_url, args.timeout)
        fingerprint = collector.page_fingerprint(records)
        if actual_url in seen_urls or fingerprint in seen_fingerprints:
            raise collector.CollectionError("检测到重复URL或重复页面，停止采集")
        seen_urls.add(actual_url)
        seen_fingerprints.add(fingerprint)
        data = html.encode("utf-8")
        name = f"page_{number:03}.html"
        collector.atomic_bytes(folder / name, data)  # 保存完整page_source，不截断长HTML。
        page = {"url": actual_url, "requested_url": requested_url, "file": name,
                "sha256": collector.digest(data), "captured_at": collector.now(),
                "property_count": len(records), "html_chars": len(html),
                "next": {"href": button["href"], "disabled": button["disabled"], "urljoin_result": following}}
        manifest["pages"].append(page)
        collector.save_json(folder / "manifest.json", manifest)
        all_records.extend(records)
        emit("page_saved", page=number, url=actual_url, count=len(records),
             accumulated=len(all_records), next_href=button["href"], next_url=following)
        if number == 1 or number == args.pages or following is None:
            driver.save_screenshot(str(folder / f"page_{number:03}.png"))
        if following is None:
            manifest.update(complete=True, scope_complete=True, stop_reason="下一页明确禁用，已到末页")
            break
        if number == args.pages:
            manifest.update(complete=False, scope_complete=True,
                            stop_reason=f"按要求保存前{args.pages}页；本页仍有下一页")
            break
        requested_url = collector.checked_url(following, actual_url)
        time.sleep(args.delay)
    collector.save_json(folder / "manifest.json", manifest)
    return all_records


def write_run_csv(folder, records):
    unique = list(dict.fromkeys(records))
    if not unique:
        raise collector.CollectionError("没有真实记录，不生成空CSV")
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(collector.FIELDS)
    writer.writerows(unique)
    target = folder / "houseinfo.csv"
    collector.atomic_bytes(target, stream.getvalue().encode("utf-8-sig"))
    if collector.read_csv_records(target) != unique:
        raise collector.CollectionError("本次CSV回读不一致")
    return target, len(unique)


def main(argv=None):
    args = arguments(argv)
    run_id = datetime.now(collector.SHANGHAI).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    folder = BASE / "evidence" / "runs" / ("browser_" + run_id)
    folder.mkdir(parents=True, exist_ok=False)
    result = {"state": "working", "started_at": collector.now(), "requested_pages": args.pages,
              "source_mode": "selenium_browser", "saved_pages": 0, "csv_path": None,
              "standard_csv_modified": False, "database_modified": False}
    manifest = {"source": "browser_saved", "provider": "browser_collect.py 使用Selenium保存教学站真实DOM",
                "capture_method": "browser_dom_serialization", "captured_at": collector.now(),
                "pages": [], "complete": False, "scope_complete": False,
                "collection_scope": {"type": "first_pages", "page_limit": args.pages, "user_requested": True}}

    def emit(event, **details):
        line = json.dumps({"time": collector.now(), "event": event, **details}, ensure_ascii=False)
        print(line, flush=True)
        with (folder / "run.jsonl").open("a", encoding="utf-8") as log:
            log.write(line + "\n")

    driver = None
    code = 1
    try:
        emit("started", output=str(folder), requested_pages=args.pages)
        driver = create_driver(args)
        emit("browser_started", browser=driver.capabilities.get("browserName"),
             version=driver.capabilities.get("browserVersion"))
        records = capture_pages(driver, args, folder, emit, manifest)
        csv_path, unique_count = write_run_csv(folder, records)
        result.update(state="ready", saved_pages=len(manifest["pages"]), raw_count=len(records),
                      deduplicated_count=unique_count, duplicates=len(records) - unique_count,
                      csv_path=str(csv_path), csv_sha256=collector.sha256_file(csv_path),
                      scope_complete=True, site_complete=manifest["complete"],
                      manifest_path=str(folder / "manifest.json"), reason=manifest["stop_reason"])
        emit("completed", **result)
        print("本次HTML、截图、CSV及日志：", folder)
        print("已有lab02/data/houseinfo.csv及MySQL数据保持不变。")
        code = 0
    except Exception as exc:
        state = getattr(exc, "kind", "error")
        result.update(state=state, saved_pages=len(manifest["pages"]), reason=f"{type(exc).__name__}: {exc}")
        if driver is not None:
            try:
                collector.atomic_bytes(folder / "failure_page.html", driver.page_source.encode("utf-8"))
                driver.save_screenshot(str(folder / "failure_page.png"))
                result["failure_url"] = driver.current_url
            except Exception as evidence_error:
                result["evidence_error"] = str(evidence_error)
        emit("stopped", **result)
        code = 2 if state == "blocked_source" else 1
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception as close_error:
                result["browser_close_error"] = str(close_error)
        result["finished_at"] = collector.now()
        collector.save_json(folder / "result.json", result)
        collector.save_json(BASE / "browser_last_run.json", result)
    return code


if __name__ == "__main__":
    sys.exit(main())
