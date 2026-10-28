"""真实CSV入库入口：核实来源链，自动取得跨页样本索引，再独立重跑验收。

在现有课程容器/Jupyter终端执行：
    cd /home/pwuser/workspace/bigdata-collection-labs-112404260129/lab02
    python part3_storage/run_real_import.py

本入口不采集、不建表、不自行写CSV或状态；真实写入只委托 storage.py。
生成的证据不会把未执行、失败或结果未知写成入库成功。
"""

import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
LAB = BASE.parent
FIELDS = ("title", "house", "address", "struct", "area", "floor", "maketime", "price")
TZ = timezone(timedelta(hours=8))


def now():
    return datetime.now(TZ).isoformat(timespec="seconds")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def text(value):
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value


def current_finished_event(stdout):
    events = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(event, dict) and event.get("event") == "finished" and event.get("stage") == 3:
            events.append(event)
    return events[-1] if events else None


def verify_three_way_samples(source_samples):
    """真实网页来源记录→CSV→数据库逐字段对应，不只比较样本条数。"""
    verified = []
    for phase in ("run", "rerun"):
        path = BASE / "evidence" / f"samples_{phase}.json"
        result = read_json(path)
        if not result.get("samples_match") or not result.get("all_csv_rows_present"):
            raise RuntimeError(f"{phase}：并非全部真实CSV记录已核对")
        database_samples = {sample["role"]: sample for sample in result["samples"]}
        for role in ("first", "cross_page", "last"):
            source = source_samples[role]
            target = database_samples.get(role)
            if (not target or target["csv_line"] != source["csv_line"]
                    or not target.get("all_eight_equal") or not target.get("matched_ids")):
                raise RuntimeError(f"{phase}：{role} 的真实来源/CSV行号/数据库记录不一致")
            if set(target["fields"]) != set(FIELDS):
                raise RuntimeError(f"{phase}：{role} 不含完整8字段")
            for field in FIELDS:
                pair = target["fields"][field]
                if not pair.get("equal") or pair["csv"] != source["record"][field] or pair["database"] != source["record"][field]:
                    raise RuntimeError(f"{phase}：{role}.{field} 网页、CSV与数据库不完全相同")
            verified.append({"phase": phase, "sample": role, "url": source["url"],
                             "page": source["page"], "page_row": source["page_row"],
                             "csv_line": source["csv_line"], "database_ids": target["matched_ids"],
                             "record": source["record"], "all_eight_equal": True})
    return verified


def main():
    run_id = datetime.now(TZ).strftime("%Y%m%d_%H%M%S") + f"_{os.getpid()}"
    log_dir = BASE / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / f"real_pipeline_{run_id}.stdout.txt"
    stderr_path = log_dir / f"real_pipeline_{run_id}.stderr.txt"
    evidence = {"stage": 3, "run_id": run_id, "started_at": now(), "checked_at": now(),
                "state": "not_executed", "import_process_started": False,
                "actual_import_completed": False, "actual_write_state": "not_attempted",
                "before_count": None, "after_count": None, "inserted_count": None,
                "rerun_inserted_count": None, "samples_match": None,
                "source_samples": None, "csv_sha256": None, "returncode": None,
                "stdout_file": str(stdout_path.relative_to(BASE)),
                "stderr_file": str(stderr_path.relative_to(BASE)), "reason": "尚未校验真实来源"}
    stdout = stderr = ""
    code = 1
    try:
        sys.path.insert(0, str(LAB))
        from part2_collection.collect_houses import verify_csv_bundle

        manifest = verify_csv_bundle()  # 实际重读、重解析HTML/分页/CSV；不触网、不写CSV。
        second = read_json(LAB / "part2_collection" / "status.json")
        csv_path = LAB / "data" / "houseinfo.csv"
        digest = sha256(csv_path)
        if (second.get("stage") != 2 or second.get("state") != "ready"
                or second.get("csv_sha256") != digest or manifest["csv_sha256"] != digest):
            raise RuntimeError("第二阶段尚未ready，或CSV字节哈希与已核验来源不一致")
        samples = {sample["sample"]: sample for sample in manifest["samples"]}
        if set(samples) != {"first", "cross_page", "last"}:
            raise RuntimeError("来源清单没有首条、跨页和末条的真实样本")
        for role, sample in samples.items():
            if (not sample.get("html_csv_exact_match") or set(sample["record"]) != set(FIELDS)
                    or isinstance(sample["csv_line"], bool) or not isinstance(sample["csv_line"], int)
                    or sample["csv_line"] < 2):
                raise RuntimeError(f"真实来源样本不完整：{role}")
        cross_index = samples["cross_page"]["csv_line"] - 2
        evidence.update(csv_sha256=digest, source_mode=manifest["source_mode"],
                        source_samples=list(samples.values()), cross_page_index=cross_index,
                        csv_rows=manifest["deduplicated_count"],
                        source_run_id=manifest["run_id"],
                        storage_script_sha256=sha256(BASE / "storage.py"))
        command = [sys.executable, str(BASE / "storage.py"), "run", "--cross-page-index", str(cross_index)]
        evidence.update(import_process_started=True, actual_write_state="unknown", command=command)
        try:
            result = subprocess.run(command, cwd=str(LAB), capture_output=True,
                                    text=True, encoding="utf-8", timeout=360)
            stdout, stderr = result.stdout, result.stderr
            evidence["returncode"] = result.returncode
        except subprocess.TimeoutExpired as exc:
            stdout, stderr = text(exc.stdout), text(exc.stderr)
            raise RuntimeError("真实入库入口超时；已提交数据可能保留，不能推断写入条数") from exc
        event = current_finished_event(stdout)
        if event is None:
            raise RuntimeError("本次子进程没有最终状态事件，不能使用可能残留的旧status判为成功")
        for key in ("before_count", "after_count", "inserted_count", "rerun_inserted_count", "samples_match", "actual_import_completed"):
            evidence[key] = event.get(key)
        evidence["storage_reason"] = event.get("reason")
        evidence["actual_write_state"] = "recorded_by_this_process"
        if result.returncode != 0:
            raise RuntimeError(f"真实入库流程退出码为{result.returncode}：{event.get('reason')}")
        status = read_json(BASE / "status.json")
        if any(status.get(key) != event.get(key) for key in ("checked_at", "state", "csv_sha256", "before_count", "after_count", "inserted_count", "rerun_inserted_count", "final_db_fingerprint")):
            raise RuntimeError("状态文件与本次子进程最终事件不符，可能存在并发运行")
        if (status.get("state") != "ready" or not status.get("actual_import_completed")
                or status.get("csv_sha256") != digest or status.get("rerun_inserted_count") != 0
                or not status.get("samples_match") or not status.get("cross_page_sample_verified")):
            raise RuntimeError("真实入库、独立重跑或样本验收条件不完整")
        if status["after_count"] - status["before_count"] != status["inserted_count"]:
            raise RuntimeError("真实入库前后条数与新增数量不一致")
        # 防止入库期间来源文件/程序被另一进程替换。
        final_manifest = verify_csv_bundle()
        if (sha256(csv_path) != digest or final_manifest != manifest
                or sha256(BASE / "storage.py") != evidence["storage_script_sha256"]):
            raise RuntimeError("入库期间CSV、来源清单或入库程序发生变化，停止自动验收")
        evidence["three_way_samples"] = verify_three_way_samples(samples)
        evidence.update(state="ready", actual_import_completed=True,
                        reason="真实网页来源、CSV与数据库8字段一致；少量/全量入库及新进程重跑新增0通过")
        code = 0
    except Exception as exc:
        evidence.update(state="error" if evidence["import_process_started"] else "not_executed",
                        reason=f"{type(exc).__name__}: {exc}")
    finally:
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")
        evidence["checked_at"] = now()
        paths = [LAB / "data" / "houseinfo.csv", LAB / "part2_collection" / "csv_provenance.json",
                 BASE / "storage.py", BASE / "run_real_import.py", BASE / "status.json",
                 BASE / "evidence" / "first_import_result.json", BASE / "evidence" / "rerun_result.json",
                 BASE / "evidence" / "samples_run.json", BASE / "evidence" / "samples_rerun.json",
                 stdout_path, stderr_path]
        evidence["files"] = [{"path": str(path.relative_to(LAB)).replace("\\", "/"),
                              "bytes": path.stat().st_size, "sha256": sha256(path)}
                             for path in paths if path.is_file()]
        save_json(BASE / "evidence" / "real_pipeline_result.json", evidence)
        # 每次运行另存一份，避免后续重跑丢失首次实际新增条数的证据。
        save_json(BASE / "evidence" / f"real_pipeline_result_{run_id}.json", evidence)
    if stdout:
        print(stdout, end="" if stdout.endswith("\n") else "\n")
    if stderr:
        print(stderr, file=sys.stderr, end="" if stderr.endswith("\n") else "\n")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
