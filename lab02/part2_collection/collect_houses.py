"""实验二第二阶段：仅教学站采集、两页试采、CSV 与来源链验收。

课程容器/Jupyter 终端（在 lab02 中）：
  python part2_collection/collect_houses.py trial
  python part2_collection/collect_houses.py collect
  python part2_collection/collect_houses.py verify
Notebook 可 import 后显式调用 main(["trial"])；main([]) 只显示帮助。

教师快照 manifest 格式（本程序不会生成示例房源）：
  {"source":"teacher_provided", "provider":"实际提供者/说明",
   "pages":[{"url":"http://www.bspider.top/anjuke/",
             "file":"第一页.html", "sha256":"实际文件SHA256"}, ...]}
运行 trial/collect 时加 --offline-manifest 实际清单路径；属于离线回放。

浏览器真实DOM快照：使用 --browser-manifest 实际清单路径，清单必须明确
source=browser_saved、capture_method=browser_dom_serialization、provider、captured_at，
每页含 url/file/sha256/captured_at/property_count。此模式为 browser_snapshot，
是浏览器正常加载后保存DOM的回放，不是requests成功采集或教师提供快照。
"""

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

FIELDS = ("title", "house", "address", "struct", "area", "floor", "maketime", "price")
BASE_URL = "http://www.bspider.top/anjuke/"
PART_DIR = Path(__file__).resolve().parent
LAB_DIR = PART_DIR.parent
CSV_PATH = LAB_DIR / "data" / "houseinfo.csv"
STATUS_PATH = PART_DIR / "status.json"
SHANGHAI = timezone(timedelta(hours=8))


class CollectionError(RuntimeError):
    def __init__(self, message, details=None, kind="error"):
        super().__init__(message)
        self.details = details or {}
        self.kind = kind


def now():
    return datetime.now(SHANGHAI).isoformat(timespec="seconds")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return digest(Path(path).read_bytes())


def atomic_bytes(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_json(path, value):
    atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def relative(path):
    return str(Path(path).resolve().relative_to(PART_DIR)).replace("\\", "/")


def evidence_path(value):
    path = (PART_DIR / value).resolve()
    if not path.is_relative_to(PART_DIR) or not path.is_file():
        raise CollectionError("证据路径越界或文件不存在", {"path": str(value)})
    return path


def checked_url(href, current_url=BASE_URL):
    """读取 href 后用 urljoin 补全；在发请求前限定域名、端口、目录。"""
    if not isinstance(href, str) or not href.strip():
        raise CollectionError("链接为空")
    try:
        parts = urlsplit(urljoin(current_url, href.strip()))
        expected_port = 80 if parts.scheme == "http" else 443
        path = parts.path
        decoded = path
        for _ in range(3):
            updated = unquote(decoded)
            if updated == decoded:
                break
            decoded = updated
        if (parts.scheme not in ("http", "https") or parts.hostname != "www.bspider.top"
                or parts.username is not None or parts.password is not None
                or parts.port not in (None, expected_port)
                or not decoded.startswith("/anjuke/") or "\\" in decoded
                or any(segment in (".", "..") for segment in decoded.split("/"))
                or any(ord(character) < 32 for character in href)):
            raise CollectionError("链接越出教学站允许范围", {"href": href})
    except ValueError as exc:
        raise CollectionError("链接端口或格式无效", {"href": href}) from exc
    return urlunsplit((parts.scheme, "www.bspider.top", parts.path, parts.query, ""))


def parse_page(html, url=BASE_URL):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    text = soup.get_text(strip=True)
    markers = ("访问验证", "系统检测到您正在使用网页抓取工具", "请完成验证", "安全验证", "人机验证")
    if any(marker in title or marker in text for marker in markers):
        raise CollectionError("教学站返回访问验证页，立即停止自动采集",
                              {"url": url, "title": title, "property_count": len(soup.select("div.property"))},
                              kind="blocked_source")
    if not soup.select("div.property"):
        raise CollectionError("房源列表为空或页面结构异常", {"url": url, "title": title})
    return soup


def node_text(row, selectors, required=True):
    for selector in selectors:
        node = row.select_one(selector)
        if node is not None:
            value = node.get_text(strip=True)  # 不在地址相邻子标签间额外插入空格
            if value:
                return value
    if required:
        raise CollectionError("缺少必要字段", {"selectors": list(selectors)})
    return ""


def parse_record(row):
    """手册给出的选择器；须以真实页面逐字段核对，异常时不跳过记录。"""
    title = node_text(row, (".property-content-title-name", ".property-content-title h3", "h3"))
    house = node_text(row, (".property-content-info-comm-name", "[class*='comm-name']"))
    address = node_text(row, (".property-content-info-comm-address", "[class*='comm-address']"))
    attributes = [node.get_text(strip=True) for node in row.select(".property-content-info-text")]
    if not attributes:
        raise CollectionError("未找到房源属性组 .property-content-info-text")
    struct = next((value for value in attributes if re.fullmatch(r"\d+室(?:\d+厅)?(?:\d+卫)?", value)), "")
    area = next((value for value in attributes if re.fullmatch(r"\d+(?:\.\d+)?\s*(?:平方米|㎡|m²|m2|平米)", value, re.I)), "")
    floor = next((value for value in attributes if "层" in value and
                  re.search(r"楼层|共\s*\d+\s*层|[高中低]层|\d+\s*层", value)), "")
    maketime = next((value for value in attributes if re.search(r"(?:19|20)\d{2}\s*年", value)), "")
    price = node_text(row, (".property-price-average", "[class*='price-average']"))
    if not struct or not area or not floor:
        raise CollectionError("户型、面积或楼层缺失/不明确，不能把朝向当楼层", {"attributes": attributes})
    if "万" in price or not re.search(r"元\s*/\s*(?:㎡|m²|m2|平米|平方米)|元每(?:平方米|平米)", price, re.I):
        raise CollectionError("无法确认每平方米单价，禁止使用总价", {"price": price})
    return (title, house, address, struct, area, floor, maketime, price)


def next_page(soup, current_url):
    pager = soup.select_one(".pagination, .multi-page, .pagination-wrap, .pagination-container, .pager")
    if pager is None:
        raise CollectionError("分页区域消失，不能认定末页")
    button = pager.select_one(".next")
    if button is None:
        button = next((node for node in pager.select("a, span, button") if node.get_text(strip=True) == "下一页"), None)
    if button is None:
        raise CollectionError("下一页按钮缺失，不能认定末页")
    classes = button.get("class", [])
    disabled = (button.has_attr("disabled") or str(button.get("aria-disabled", "")).lower() == "true"
                or any(value in ("disabled", "disable", "next-disabled", "is-disabled") for value in classes))
    href = button.get("href", "")
    info = {"html": str(button), "href": href, "disabled": disabled}
    if disabled:
        return None, info
    if not href or href.strip() == "#" or href.lower().startswith("javascript:"):
        raise CollectionError("下一页没有有效 href，且没有明确禁用标志", info)
    following = checked_url(href, current_url)  # urljoin 位于 checked_url；先校验再请求
    info["urljoin_result"] = following
    return following, info


def page_fingerprint(records):
    return digest(json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def checked_browser_navigation(requested_url, actual_url):
    """只接受相同地址或同站、同路径/查询的HTTP到HTTPS升级。"""
    requested, actual = checked_url(requested_url), checked_url(actual_url)
    if requested != actual:
        before, after = urlsplit(requested), urlsplit(actual)
        if (before.scheme != "http" or after.scheme != "https"
                or (before.hostname, before.path, before.query) != (after.hostname, after.path, after.query)):
            raise CollectionError("浏览器实际落地地址只允许同站同路径查询的HTTP到HTTPS升级")
    return requested, actual


class Run:
    def __init__(self, command, mode):
        self.run_id = datetime.now(SHANGHAI).strftime("%Y%m%dT%H%M%S_%f") + "_" + uuid.uuid4().hex[:8]
        self.directory = PART_DIR / "evidence" / "runs" / self.run_id
        self.directory.mkdir(parents=True, exist_ok=False)
        self.result = {"run_id": self.run_id, "command": command, "source_mode": mode,
                       "started_at": now(), "pages": [], "events": [], "complete": False}
        self.last_request = None

    def event(self, message, **details):
        item = {"at": now(), "message": message, **details}
        self.result["events"].append(item)
        print(json.dumps(item, ensure_ascii=False), flush=True)
        save_json(self.directory / "run.json", self.result)


class PageSource:
    def __init__(self, run, delay=1.0, offline_manifest=None, browser_manifest=None):
        if not math.isfinite(delay) or delay < 1:
            raise CollectionError("请求间隔必须至少1秒")
        self.run, self.delay = run, delay
        self.sources = {}
        self.manifest_info = None
        self.source_mode = "browser_snapshot" if browser_manifest else "teacher_snapshot"
        if offline_manifest and browser_manifest:
            raise CollectionError("教师快照与浏览器快照参数不能同时使用")
        if offline_manifest or browser_manifest:
            manifest_path = Path(offline_manifest or browser_manifest).resolve()
            manifest = load_json(manifest_path)
            expected_source = "browser_saved" if browser_manifest else "teacher_provided"
            if (manifest.get("source") != expected_source or not str(manifest.get("provider", "")).strip()
                    or not isinstance(manifest.get("pages"), list) or not manifest["pages"]):
                raise CollectionError(f"快照清单必须明确 source={expected_source}、provider 和非空 pages")
            if browser_manifest and (manifest.get("capture_method") != "browser_dom_serialization"
                                     or not str(manifest.get("captured_at", "")).strip()):
                raise CollectionError("浏览器快照须明确DOM序列化方法及真实捕获时间")
            actual_urls = set()
            for item in manifest["pages"]:
                url = checked_url(item["url"])
                requested_url = checked_url(item.get("requested_url", item["url"]))
                if browser_manifest:
                    requested_url, url = checked_browser_navigation(requested_url, url)
                elif requested_url != url:
                    raise CollectionError("教师快照不能声明不同的请求与实际地址")
                path = (manifest_path.parent / item["file"]).resolve()
                expected = item["sha256"].lower()
                if (not path.is_relative_to(manifest_path.parent) or not path.is_file()
                        or not re.fullmatch(r"[0-9a-f]{64}", expected) or requested_url in self.sources or url in actual_urls
                        or sha256_file(path) != expected):
                    raise CollectionError("快照文件缺失、越界、URL重复或SHA256不符")
                if browser_manifest:
                    count = item.get("property_count")
                    if (not str(item.get("captured_at", "")).strip() or isinstance(count, bool)
                            or not isinstance(count, int) or count < 0):
                        raise CollectionError("浏览器每页快照须有真实捕获时间和非负整数房源容器数")
                actual_urls.add(url)
                self.sources[requested_url] = {"path": path, "sha256": expected, "url": url,
                                     "captured_at": item.get("captured_at"),
                                     "property_count": item.get("property_count")}
            self.manifest_info = {"source": expected_source, "provider": manifest["provider"],
                                  "manifest_path": str(manifest_path), "manifest_sha256": sha256_file(manifest_path)}
            if browser_manifest:
                self.manifest_info.update(capture_method=manifest["capture_method"], captured_at=manifest["captured_at"])
            manifest_key = "browser_manifest" if browser_manifest else "teacher_manifest"
            save_json(run.directory / (manifest_key + ".json"), manifest)
            run.result[manifest_key] = self.manifest_info
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})

    def close(self):
        self.session.close()

    def get(self, url, page_number):
        url = checked_url(url)
        if self.sources:
            if url not in self.sources:
                raise CollectionError("缺少当前URL对应的教师真实快照", {"url": url})
            item = self.sources[url]
            raw = item["path"].read_bytes()
            if digest(raw) != item["sha256"]:
                raise CollectionError("来源快照在运行中发生变化")
            html = raw.decode("utf-8-sig")
            metadata = {"requested_url": url, "url": item["url"], "source_mode": self.source_mode,
                        "source_file": str(item["path"]), "encoding": "utf-8-sig",
                        "status_code": None, "offline_replay": True}
            if self.source_mode == "browser_snapshot":
                metadata.update(browser_sha256=item["sha256"], captured_at=item["captured_at"],
                                browser_property_count=item["property_count"],
                                capture_method="browser_dom_serialization",
                                content_representation="browser_dom_utf8")
                actual_count = len(BeautifulSoup(html, "html.parser").select("div.property"))
                if actual_count != item["property_count"]:
                    raise CollectionError("浏览器快照容器数与捕获清单不符")
            else:
                metadata["teacher_sha256"] = item["sha256"]
            return self.save_response(raw, html, metadata, page_number, 0)
        current = url
        redirects_seen = set()
        for hop in range(4):
            if current in redirects_seen:
                raise CollectionError("同站重定向形成循环", {"url": current})
            redirects_seen.add(current)
            if self.run.last_request is not None:
                time.sleep(self.delay)  # 前一响应处理完后，进入下一请求前明确等待至少1秒
            self.run.last_request = time.monotonic()
            self.run.event("请求教学站", page=page_number, url=current, redirect_hop=hop)
            response = self.session.get(current, timeout=30, allow_redirects=False)
            response.encoding = response.apparent_encoding or "utf-8"
            html = response.text
            metadata = {"requested_url": url, "url": current, "source_mode": "online",
                        "status_code": response.status_code, "encoding": response.encoding,
                        "content_type": response.headers.get("Content-Type", ""),
                        "location": response.headers.get("Location", ""), "redirect_hop": hop}
            html, metadata = self.save_response(response.content, html, metadata, page_number, hop)
            title = BeautifulSoup(html, "html.parser").title
            marker_text = BeautifulSoup(html, "html.parser").get_text(strip=True)
            if any(marker in marker_text for marker in ("访问验证", "系统检测到您正在使用网页抓取工具", "人机验证", "安全验证", "请完成验证")):
                raise CollectionError("教学站返回访问验证页，停止自动采集",
                                      {"url": current, "title": title.get_text(strip=True) if title else "",
                                       "response": metadata}, kind="blocked_source")
            if 300 <= response.status_code < 400:
                if hop == 3 or not metadata["location"]:
                    raise CollectionError("同站重定向超过3次或缺少Location", metadata)
                current = checked_url(metadata["location"], current)
                continue
            response.raise_for_status()
            return html, metadata
        raise CollectionError("重定向未结束")

    def save_response(self, raw, html, metadata, page_number, hop):
        stem = f"page_{page_number:03}_hop_{hop}"
        browser = metadata["source_mode"] == "browser_snapshot"
        raw_path = self.run.directory / (stem + ("_browser_dom.html" if browser else ".bin"))
        html_path = self.run.directory / (stem + ".html")
        atomic_bytes(raw_path, raw)
        atomic_bytes(html_path, html.encode("utf-8"))
        soup = BeautifulSoup(html, "html.parser")
        metadata.update(checked_at=now(),
                        decoded_html_path=relative(html_path), decoded_html_sha256=sha256_file(html_path),
                        title=soup.title.get_text(strip=True) if soup.title else "",
                        property_count=len(soup.select("div.property")))
        if browser:
            metadata.update(snapshot_path=relative(raw_path), snapshot_sha256=digest(raw))
        else:
            metadata.update(raw_path=relative(raw_path), raw_sha256=digest(raw))
        save_json(self.run.directory / (stem + ".json"), metadata)
        return html, metadata


def read_csv_records(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != list(FIELDS):
            raise CollectionError("CSV 表头或顺序不符合8字段", {"header": reader.fieldnames})
        records = []
        for line, row in enumerate(reader, 2):
            if None in row or any(row[field] is None for field in FIELDS):
                raise CollectionError("CSV数据行不是恰好8字段", {"line": line})
            records.append(tuple(row[field] for field in FIELDS))
    if not records:
        raise CollectionError("CSV没有数据")
    if len(records) != len(set(records)):
        raise CollectionError("CSV含8字段完全相同的重复记录")
    return records


def verify_response(metadata):
    if metadata.get("source_mode") not in ("online", "teacher_snapshot", "browser_snapshot"):
        raise CollectionError("不支持的页面来源模式")
    browser = metadata["source_mode"] == "browser_snapshot"
    raw_path = evidence_path(metadata["snapshot_path"] if browser else metadata["raw_path"])
    html_path = evidence_path(metadata["decoded_html_path"])
    raw, html_bytes = raw_path.read_bytes(), html_path.read_bytes()
    source_sha256 = metadata["snapshot_sha256"] if browser else metadata["raw_sha256"]
    if digest(raw) != source_sha256 or digest(html_bytes) != metadata["decoded_html_sha256"]:
        raise CollectionError("网页响应证据SHA256不符")
    # requests.text 遇无效字符使用 replacement；保留并验证同一解码结果。
    decoded = raw.decode(metadata["encoding"], errors="replace")
    if decoded.encode("utf-8") != html_bytes:
        raise CollectionError("原始字节与解码HTML不对应")
    if metadata["source_mode"] == "online" and metadata["status_code"] != 200:
        raise CollectionError("房源来源响应并非HTTP 200")
    if metadata["source_mode"] == "teacher_snapshot" and digest(raw) != metadata["teacher_sha256"]:
        raise CollectionError("教师快照SHA256不符")
    if browser:
        checked_browser_navigation(metadata["requested_url"], metadata["url"])
        if (metadata.get("capture_method") != "browser_dom_serialization"
                or metadata.get("content_representation") != "browser_dom_utf8"
                or metadata.get("status_code") is not None or not metadata.get("captured_at")
                or digest(raw) != metadata.get("browser_sha256")):
            raise CollectionError("浏览器DOM快照来源标记或SHA256不符，不能当作HTTP响应")
        actual_count = len(BeautifulSoup(decoded, "html.parser").select("div.property"))
        if actual_count != metadata.get("browser_property_count"):
            raise CollectionError("浏览器DOM快照房源容器数与来源标记不符")
    return decoded


def verify_pages(pages, require_complete=False, source_mode=None):
    if not pages:
        raise CollectionError("没有实际解析页面")
    all_records, seen_urls, seen_fingerprints = [], set(), set()
    expected_url = BASE_URL
    for index, page in enumerate(pages, 1):
        if source_mode is not None and page["response"].get("source_mode") != source_mode:
            raise CollectionError("来源链页面模式与本次清单模式不一致")
        if page["page"] != index or page["requested_url"] != expected_url:
            raise CollectionError("页面来源链顺序或下一页URL不符")
        url = checked_url(page["url"])
        if url in seen_urls or page["fingerprint"] in seen_fingerprints:
            raise CollectionError("来源链有重复页面或URL")
        seen_urls.add(url)
        seen_fingerprints.add(page["fingerprint"])
        soup = parse_page(verify_response(page["response"]), url)
        records = [parse_record(row) for row in soup.select("div.property")]
        if page_fingerprint(records) != page["fingerprint"] or len(records) != page["count"]:
            raise CollectionError("来源网页重解析与记录指纹不符")
        saved_records = load_json(evidence_path(page["records_path"]))
        if digest(json.dumps(saved_records, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) != page["fingerprint"]:
            raise CollectionError("保存的页面记录与来源HTML不符")
        following, button = next_page(soup, url)
        if following != page["next_url"] or button != page["next_button"]:
            raise CollectionError("分页节点或下一页URL验证失败")
        if following is None and index != len(pages):
            raise CollectionError("末页后仍然存在页面记录")
        expected_url = following
        all_records.extend(records)
    if require_complete and (pages[-1]["next_url"] is not None or not pages[-1]["next_button"]["disabled"]):
        raise CollectionError("没有明确禁用的末页按钮，不能完成采集")
    return all_records


def sample_checks(pages, raw_records, unique_records):
    if len(pages) < 2:
        raise CollectionError("没有两页真实数据，不能核验跨页样本")
    positions = ((0, 1, 1), (pages[0]["count"], 2, 1), (len(raw_records) - 1, len(pages), pages[-1]["count"]))
    result = []
    for label, (position, page_number, row_number) in zip(("first", "cross_page", "last"), positions):
        record = tuple(raw_records[position])
        csv_index = unique_records.index(record)
        result.append({"sample": label, "page": page_number, "url": pages[page_number - 1]["url"],
                       "page_row": row_number, "csv_line": csv_index + 2,
                       "record": dict(zip(FIELDS, record)), "html_csv_exact_match": True})
    return result


def is_first_pages_scope(manifest):
    """仅接受明确由用户指定、已全部保存的前N页范围；不等于站点末页。"""
    scope = manifest.get("collection_scope")
    if scope is None:
        return False
    limit = scope.get("page_limit") if isinstance(scope, dict) else None
    if (not isinstance(scope, dict) or scope.get("type") != "first_pages"
            or scope.get("user_requested") is not True or isinstance(limit, bool)
            or not isinstance(limit, int) or limit < 2
            or manifest.get("complete") is not False or manifest.get("scope_complete") is not True
            or len(manifest.get("pages", [])) != limit):
        raise CollectionError("前N页范围声明无效或指定页数尚未保存齐全")
    return True


def verify_csv_bundle():
    """核对标准CSV、来源指针、保存的真实网页、分页、去重与三条样本。"""
    if not CSV_PATH.is_file():
        raise CollectionError("标准CSV尚不存在，不能验收或供第三阶段使用", kind="blocked_source")
    pointer_path = PART_DIR / "csv_provenance.json"
    if not pointer_path.is_file():
        raise CollectionError("已有CSV没有可验证来源，保留该文件，不覆盖")
    pointer = load_json(pointer_path)
    manifest_path = evidence_path(pointer["manifest_path"])
    if sha256_file(manifest_path) != pointer["manifest_sha256"]:
        raise CollectionError("CSV来源清单SHA256不符")
    manifest = load_json(manifest_path)
    limited = is_first_pages_scope(manifest)
    if (manifest.get("stage") != 2 or (not limited and not manifest.get("complete"))
            or manifest.get("source_mode") not in ("online", "teacher_snapshot", "browser_snapshot")):
        raise CollectionError("CSV来源未明确完整采集")
    if sha256_file(CSV_PATH) != manifest["csv_sha256"]:
        raise CollectionError("标准CSV与来源清单SHA256不符，保留现有文件")
    raw_records = verify_pages(manifest["pages"], require_complete=not limited, source_mode=manifest["source_mode"])
    unique = list(dict.fromkeys(raw_records))
    actual = read_csv_records(CSV_PATH)
    if actual != unique or manifest["raw_count"] != len(raw_records) or manifest["deduplicated_count"] != len(unique):
        raise CollectionError("CSV回读、网页来源或去重条数不一致")
    samples = sample_checks(manifest["pages"], raw_records, unique)
    if samples != manifest["samples"]:
        raise CollectionError("首条、跨页、末条样本来源不一致")
    return manifest


def write_csv_bundle(run):
    pages = run.result["pages"]
    limited = is_first_pages_scope(run.result)
    raw_records = verify_pages(pages, require_complete=not limited, source_mode=run.result["source_mode"])
    unique = list(dict.fromkeys(raw_records))  # 按8字段完全相同去重，保留首次出现顺序
    samples = sample_checks(pages, raw_records, unique)
    if CSV_PATH.exists():
        verify_csv_bundle()  # 不明来源、被修改的用户CSV一律保留
        atomic_bytes(run.directory / "previous_houseinfo.csv", CSV_PATH.read_bytes())
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".houseinfo.", suffix=".tmp", dir=CSV_PATH.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8-sig", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(FIELDS)
            writer.writerows(unique)
            output.flush()
            os.fsync(output.fileno())
        if read_csv_records(temporary) != unique:
            raise CollectionError("CSV临时文件回读失败")
        manifest = {"stage": 2, "run_id": run.run_id, "checked_at": now(),
                    "source_mode": run.result["source_mode"], "complete": not limited,
                    "scope_complete": True, "collection_scope": run.result.get("collection_scope"),
                    "csv_path": str(CSV_PATH), "csv_sha256": sha256_file(temporary),
                    "raw_count": len(raw_records), "deduplicated_count": len(unique),
                    "duplicates": len(raw_records) - len(unique), "pages": pages,
                    "samples": samples, "fields": list(FIELDS), "roundtrip_equal": True,
                    "teacher_manifest": run.result.get("teacher_manifest"),
                    "browser_manifest": run.result.get("browser_manifest")}
        manifest_path = run.directory / "csv_manifest.json"
        save_json(manifest_path, manifest)
        os.replace(temporary, CSV_PATH)  # 临时文件完整回读后才原子替换
        save_json(PART_DIR / "csv_provenance.json", {"manifest_path": relative(manifest_path),
                                                     "manifest_sha256": sha256_file(manifest_path)})
        return verify_csv_bundle()
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def status_for(run, state, reason, manifest=None):
    # 数量反映本次实际解析结果；无已验收CSV时路径/哈希为空且complete为false。
    return {"stage": 2, "state": state, "checked_at": now(), "source_mode": run.result["source_mode"],
            "csv_path": manifest["csv_path"] if manifest else None,
            "csv_sha256": manifest["csv_sha256"] if manifest else None,
            "raw_count": manifest["raw_count"] if manifest else run.result.get("raw_count", 0),
            "deduplicated_count": manifest["deduplicated_count"] if manifest else run.result.get("deduplicated_count", 0),
            "pages": manifest["pages"] if manifest else run.result["pages"],
            "complete": bool(manifest and manifest["complete"]), "reason": reason,
            "scope_complete": bool(manifest and manifest.get("scope_complete", manifest["complete"])),
            "collection_scope": manifest.get("collection_scope") if manifest else run.result.get("collection_scope"),
            "run_id": run.run_id, "run_path": relative(run.directory / "run.json")}


def update_status(run, state, reason, manifest=None):
    # 探测不改写既有ready；探测结果保存在自己独立的run目录。
    if run.result["command"] == "probe" and STATUS_PATH.is_file():
        try:
            previous = load_json(STATUS_PATH)
        except (OSError, ValueError):
            previous = {}
        if previous.get("state") == "ready":
            run.result["status_preserved"] = "existing_ready"
            return
    save_json(STATUS_PATH, status_for(run, state, reason, manifest))


def load_trial(mode, manifest_info):
    pointer = load_json(PART_DIR / "latest_trial.json")
    trial_path = evidence_path(pointer["trial_path"])
    if sha256_file(trial_path) != pointer["trial_sha256"]:
        raise CollectionError("两页试采清单SHA256不符")
    trial = load_json(trial_path)
    if trial.get("source_mode") != mode or not trial.get("trial_verified") or len(trial["pages"]) != 2:
        raise CollectionError("必须先完成同一来源模式的真实两页trial")
    if mode == "teacher_snapshot" and trial.get("teacher_manifest") != manifest_info:
        raise CollectionError("教师快照清单与两页试采时不同，先重新trial")
    if mode == "browser_snapshot" and trial.get("browser_manifest") != manifest_info:
        raise CollectionError("浏览器DOM快照清单与两页试采时不同，先重新trial")
    verify_pages(trial["pages"], source_mode=mode)
    return trial


def collect(run, source, command, max_pages=100, take_pages=None):
    if max_pages < 2:
        raise CollectionError("安全页数上限至少为2")
    if take_pages is not None and (isinstance(take_pages, bool) or not isinstance(take_pages, int)
                                   or take_pages < 2 or take_pages > max_pages):
        raise CollectionError("明确保存的前N页范围须在2页与安全上限之间")
    trial = load_trial(run.result["source_mode"], source.manifest_info) if command == "collect" else None
    current_url, visited, fingerprints = BASE_URL, set(), set()
    collected_records = []
    for page_number in range(1, (2 if command == "trial" else take_pages or max_pages) + 1):
        current_url = checked_url(current_url)
        if current_url in visited:
            raise CollectionError("重复下一页URL，停止采集", {"url": current_url})
        visited.add(current_url)
        html, response = source.get(current_url, page_number)
        actual_url = checked_url(response["url"])
        if actual_url != current_url and actual_url in visited:
            raise CollectionError("重定向后URL重复，停止采集")
        visited.add(actual_url)
        soup = parse_page(html, actual_url)
        records = [parse_record(row) for row in soup.select("div.property")]
        fingerprint = page_fingerprint(records)
        if fingerprint in fingerprints:
            raise CollectionError("不同URL返回相同房源页面，停止采集")
        fingerprints.add(fingerprint)
        following, button = next_page(soup, actual_url)
        records_path = run.directory / f"page_{page_number:03}_records.json"
        save_json(records_path, records)
        page = {"page": page_number, "requested_url": current_url, "url": actual_url,
                "count": len(records), "fingerprint": fingerprint, "response": response,
                "records_path": relative(records_path), "next_url": following, "next_button": button}
        run.result["pages"].append(page)
        collected_records.extend(records)
        run.result.update(raw_count=len(collected_records),
                          deduplicated_count=len(set(collected_records)))
        run.event("页面解析成功", page=page_number, url=actual_url, count=len(records),
                  accumulated=sum(value["count"] for value in run.result["pages"]),
                  next_href=button["href"], next_url=following, explicitly_disabled=button["disabled"])
        if trial is not None and page_number <= 2:
            expected = trial["pages"][page_number - 1]
            if any(page[key] != expected[key] for key in ("requested_url", "url", "fingerprint", "next_url", "next_button")):
                raise CollectionError("当前前两页与两页试采不一致；停止，须重新trial")
        if command == "trial" and page_number == 2:
            verify_pages(run.result["pages"])
            run.result.update(trial_verified=True, complete=False,
                              stop_reason="两页试采结束，尚未执行完整采集")
            save_json(run.directory / "trial.json", run.result)
            save_json(PART_DIR / "latest_trial.json", {"trial_path": relative(run.directory / "trial.json"),
                                                      "trial_sha256": sha256_file(run.directory / "trial.json")})
            return None
        if command == "collect" and take_pages is not None and page_number == take_pages:
            run.result.update(complete=False, scope_complete=True,
                              collection_scope={"type": "first_pages", "page_limit": take_pages, "user_requested": True},
                              stop_reason=f"按用户要求保存前{take_pages}页，未声明到达站点末页")
            return write_csv_bundle(run)
        if following is None:
            if take_pages is not None:
                raise CollectionError("实际页面少于用户指定的前N页范围，不能声明该范围完成")
            if page_number < 2:
                raise CollectionError("首个页面已显示末页，但尚无两页试采及跨页样本，需核对来源")
            run.result.update(complete=True, stop_reason="分页区域存在且下一页按钮明确禁用")
            return write_csv_bundle(run)
        if page_number == max_pages:
            raise CollectionError("达到安全页数上限，只能中止，不能认定完成")
        current_url = following  # 下一次循环进入真实href补全得到的下一页
    raise CollectionError("分页未正常停止")


def main(argv=None):
    if argv is None and "ipykernel" in sys.modules:
        argv = []  # Jupyter注入的 -f kernel.json 不作为CLI参数
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command")
    for name in ("probe", "trial", "collect", "verify"):
        sub = subparsers.add_parser(name)
        if name != "verify":
            sub.add_argument("--delay", type=float, default=1.0)
            group = sub.add_mutually_exclusive_group()
            group.add_argument("--offline-manifest")
            group.add_argument("--browser-manifest")
        if name == "collect":
            sub.add_argument("--max-pages", type=int, default=100)
            sub.add_argument("--take-pages", type=int, help="按用户明确要求只保存前N页；不声明站点完整采集")
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    mode = ("browser_snapshot" if getattr(args, "browser_manifest", None) else
            "teacher_snapshot" if getattr(args, "offline_manifest", None) else "online")
    run = Run(args.command, mode)
    source = None
    try:
        update_status(run, "working", "正在执行：" + args.command)
        if args.command == "verify":
            manifest = verify_csv_bundle()
            run.result["source_mode"] = manifest["source_mode"]
            run.result.update(verification_passed=True, complete=manifest["complete"],
                              scope_complete=manifest.get("scope_complete", manifest["complete"]),
                              collection_scope=manifest.get("collection_scope"))
            reason = (f"用户指定前{manifest['collection_scope']['page_limit']}页范围、来源链、CSV和样本核对通过；未声明站点末页"
                      if manifest.get("collection_scope") else "标准CSV、完整分页来源链、哈希及样本核对通过")
            update_status(run, "ready", reason, manifest)
        else:
            source = PageSource(run, args.delay, args.offline_manifest, args.browser_manifest)
            if args.command == "probe":
                html, response = source.get(BASE_URL, 1)
                parse_page(html, response["url"])
                run.result["probe"] = response
                run.event("首页可匹配房源，尚未完成字段解析与采集")
                update_status(run, "working", "首页探测成功，尚未完成两页试采及CSV")
            else:
                manifest = collect(run, source, args.command, getattr(args, "max_pages", 100),
                                   getattr(args, "take_pages", None))
                if manifest:
                    run.result["csv_manifest_path"] = relative(run.directory / "csv_manifest.json")
                    reason = (f"用户指定前{manifest['collection_scope']['page_limit']}页范围、来源链、CSV和样本核对通过；未声明站点末页"
                              if manifest.get("collection_scope") else "完整末页、网页来源链、CSV回读和三条样本均核对通过")
                    update_status(run, "ready", reason, manifest)
                else:
                    update_status(run, "working", "真实两页试采通过；尚未完整采集，不提供标准CSV")
        run.result["ok"] = True
        run.event("本次运行结束", complete=run.result["complete"])
        return 0
    except Exception as exc:
        kind = exc.kind if isinstance(exc, CollectionError) else "error"
        run.result.update(ok=False, complete=False, error=str(exc), error_type=type(exc).__name__,
                          error_details=getattr(exc, "details", {}), stopped_at=now())
        try:
            update_status(run, kind, str(exc))
        except Exception as status_exc:
            run.result["status_write_error"] = str(status_exc)
        run.event("本次运行失败并停止", state=kind, reason=str(exc))
        return 2
    finally:
        if source is not None:
            source.close()
        run.result["finished_at"] = now()
        save_json(run.directory / "run.json", run.result)


if __name__ == "__main__":
    raise SystemExit(main())
