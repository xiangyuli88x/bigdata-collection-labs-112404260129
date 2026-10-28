"""第三阶段：只读取 lab02/data/houseinfo.csv，校验依赖后安全批量入库。

在课程容器/Jupyter 终端运行：
    python part3_storage/storage.py check
    python part3_storage/storage.py run
check 只读 houseinfo；事务测试仅使用当前连接的 TEMPORARY TABLE。
run 先少量真实记录、再全部，最后启动一个新 Python 进程独立重跑。
"""

import argparse
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pymysql

FIELDS = ("title", "house", "address", "struct", "area", "floor", "maketime", "price")
LIMITS = (200, 50, 200, 50, 20, 20, 20, 20)
BASE = Path(__file__).resolve().parent
LAB = BASE.parent
CSV_PATH = LAB / "data" / "houseinfo.csv"
PART1 = LAB / "part1_mysql" / "status.json"
PART2 = LAB / "part2_collection" / "status.json"
COLS = ", ".join(f"`{name}`" for name in FIELDS)
# 固定的列名和八个 %s；记录文字绝不拼入 SQL。
INSERT_SQL = f"INSERT INTO `houseinfo` ({COLS}) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"


class StorageError(RuntimeError):
    pass


class DependencyPending(StorageError):
    def __init__(self, state, message):
        super().__init__(message)
        self.state = state


def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


class Log:
    def __init__(self, label):
        folder = BASE / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / (datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{label}_{os.getpid()}.jsonl")

    def __call__(self, event, **details):
        value = {"time": now(), "event": event, **details}
        line = json.dumps(value, ensure_ascii=False, default=str)
        print(line, flush=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")


def connect():
    return pymysql.connect(
        host="mysql", port=3306, database="smartpark_lab", user="student",
        password="123456", charset="utf8mb4", autocommit=False,
        connect_timeout=10, read_timeout=30, write_timeout=30,
    )


def read_json(path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def dependencies():
    one, two = read_json(PART1), read_json(PART2)
    if two and two.get("state") == "blocked_source":
        raise DependencyPending("blocked_source", "第二阶段确认数据来源受阻：" + str(two.get("reason")))
    if not one or one.get("stage") != 1 or one.get("state") != "ready":
        raise DependencyPending("awaiting_csv", "等待第一阶段 ready 状态和实际表结构核对")
    if not two or two.get("stage") != 2 or two.get("state") != "ready":
        raise DependencyPending("awaiting_csv", "等待第二阶段 ready 状态；不读取未经确认的数据")
    if not CSV_PATH.is_file():
        raise DependencyPending("awaiting_csv", "第二阶段状态虽为 ready，但真实 houseinfo.csv 不存在")
    digest = hashlib.sha256(CSV_PATH.read_bytes()).hexdigest()
    expected = two.get("csv_sha256")
    if not expected or digest.lower() != str(expected).lower():
        raise StorageError("CSV SHA256 与第二阶段 ready 状态不符，停止入库")
    return one, two, digest


def read_csv():
    """从同一份字节计算哈希并回读；只校验，不 strip/改单位/转数字。"""
    content = CSV_PATH.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if not content.startswith(b"\xef\xbb\xbf"):
        raise StorageError("CSV 必须是第二阶段 utf-8-sig 编码文件（缺少 BOM）")
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline=""))
    if reader.fieldnames != list(FIELDS):
        raise StorageError(f"CSV 表头/顺序错误：{reader.fieldnames!r}")
    rows = []
    for number, record in enumerate(reader, start=2):
        if None in record or any(record.get(field) is None for field in FIELDS):
            raise StorageError(f"CSV 第 {number} 行不是完整的8字段记录")
        values = tuple(record[field] for field in FIELDS)
        for field, value, limit in zip(FIELDS, values, LIMITS):
            if field != "maketime" and not value.strip():
                raise StorageError(f"CSV 第 {number} 行 {field} 为空；仅建造年代允许空字符串")
            if "\x00" in value or len(value) > limit:
                raise StorageError(f"CSV 第 {number} 行 {field} 含 NUL 或超过 VARCHAR({limit})")
        rows.append(values)
    if not rows:
        raise StorageError("CSV 只有表头或没有真实房源，停止入库")
    if len(set(rows)) != len(rows):
        raise StorageError("第二阶段 CSV 仍有8字段完全相同的重复记录，停止并请第二阶段修正")
    return rows, digest


def inspect_schema(cursor):
    cursor.execute("SELECT VERSION(), DATABASE(), CURRENT_USER(), @@character_set_connection, @@autocommit")
    version, database, user, charset, autocommit = cursor.fetchone()
    info = {"version": version, "database": database, "current_user": user,
            "charset": charset, "autocommit": autocommit}
    cursor.execute("SHOW TABLES")
    info["tables"] = [item[0] for item in cursor.fetchall()]
    if "houseinfo" not in info["tables"]:
        return {**info, "structure_ok": False, "table_exists": False, "row_count": None,
                "reason": "houseinfo 尚未由第一阶段建立；第三阶段不建表"}
    cursor.execute("DESCRIBE `houseinfo`")
    description = [list(item) for item in cursor.fetchall()]
    cursor.execute("SHOW CREATE TABLE `houseinfo`")
    create_sql = cursor.fetchone()[1]
    cursor.execute("SELECT ENGINE, TABLE_COLLATION FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='houseinfo'")
    engine, collation = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) FROM `houseinfo`")
    count = cursor.fetchone()[0]
    cursor.execute(f"SELECT {COLS} FROM `houseinfo` ORDER BY `id` LIMIT 5")
    samples = [dict(zip(FIELDS, row)) for row in cursor.fetchall()]
    expected_types = [f"varchar({length})" for length in LIMITS]
    issues = []
    if [item[0] for item in description] != ["id", *FIELDS]:
        issues.append("9列名称或顺序与手册不一致")
    elif (description[0][1].lower() != "int" or description[0][3] != "PRI"
          or "auto_increment" not in description[0][5].lower()):
        issues.append("id 不是 INT AUTO_INCREMENT PRIMARY KEY")
    if len(description) == 9 and [item[1].lower() for item in description[1:]] != expected_types:
        issues.append("8字段类型或最大长度与手册不一致")
    if engine != "InnoDB" or not collation.startswith("utf8mb4_"):
        issues.append("需要 InnoDB 与 utf8mb4 才能保障本程序的事务和中文保存")
    return {**info, "table_exists": True, "description": description, "create_sql": create_sql,
            "engine": engine, "collation": collation, "row_count": count,
            "first_five": samples, "structure_ok": not issues, "issues": issues}


def snapshot(cursor, table="houseinfo", lock=False):
    if table != "houseinfo" and not table.startswith("part3_test_"):
        raise StorageError("非法目标表")
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(f"SELECT `id`, {COLS} FROM `{table}` ORDER BY `id`{suffix}")
    return tuple(tuple(item) for item in cursor.fetchall())


def fingerprint(rows):
    raw = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def stable_schema(create_sql):
    # 表选项的计数随正常插入变化，列定义的 auto_increment 必须保留。
    return re.sub(r" AUTO_INCREMENT=\d+", "", create_sql)


def field_samples(records, actual, second, cross_page_index=None):
    """0起始索引由第二阶段的真实分页来源提供，不把中间一条冒充跨页样本。"""
    indices = {"first": 0, "last": len(records) - 1}
    supplied = second.get("sample_indices", {})
    if cross_page_index is None and isinstance(supplied, dict):
        cross_page_index = supplied.get("cross_page")
    if cross_page_index is not None:
        if isinstance(cross_page_index, bool) or not isinstance(cross_page_index, int) or not 0 <= cross_page_index < len(records):
            raise StorageError("跨页样本索引无效；必须使用第二阶段真实来源对应的0起始CSV记录索引")
        indices["cross_page"] = cross_page_index
    available = {tuple(row[1:]) for row in actual}
    samples = []
    for role, index in indices.items():
        target = records[index]
        matched_rows = [row for row in actual if tuple(row[1:]) == target]
        db_values = tuple(matched_rows[0][1:]) if matched_rows else None
        samples.append({"role": role, "csv_index_zero_based": index,
                        "csv_line": index + 2, "matched_ids": [row[0] for row in matched_rows],
                        "fields": {field: {"csv": value, "database": db_values[i] if db_values else None,
                                            "equal": bool(db_values is not None and db_values[i] == value)}
                                   for i, (field, value) in enumerate(zip(FIELDS, target))},
                        "all_eight_equal": db_values == target})
    all_present = all(record in available for record in records)
    return {"all_csv_rows_present": all_present, "samples": samples,
            "cross_page_source_available": "cross_page" in indices,
            "samples_match": all_present and all(item["all_eight_equal"] for item in samples)}


def insert_batch(connection, cursor, records, expected_snapshot, log, table="houseinfo", expected_schema=None):
    """锁定完整已有记录及范围，按8字段精确比较，只追加缺失记录。"""
    try:
        connection.begin()
        if table == "houseinfo":
            current_schema = inspect_schema(cursor)
            if not current_schema["structure_ok"] or (expected_schema is not None and stable_schema(current_schema["create_sql"]) != stable_schema(expected_schema)):
                raise StorageError("事务开始时发现表结构变化，停止并保留现场")
        current = snapshot(cursor, table, lock=True)
        if current != expected_snapshot:
            raise StorageError("检测到未知并发写入/删除/修改，已停止；保留数据库现场")
        existing = {tuple(row[1:]) for row in current}
        missing = []
        for record in records:
            if record not in existing:
                missing.append(record)
                existing.add(record)
        sql = INSERT_SQL if table == "houseinfo" else INSERT_SQL.replace("`houseinfo`", f"`{table}`")
        affected = cursor.executemany(sql, missing) if missing else 0
        after = snapshot(cursor, table, lock=True)
        if affected != len(missing) or len(after) - len(current) != len(missing):
            raise StorageError("批量写入条数核对失败，撤销本次事务")
        # 保留每条既有记录；不依赖id防重，id只用于识别意外修改。
        if not set(current).issubset(set(after)):
            raise StorageError("已有记录发生变化，撤销本次事务")
        if any(record not in {row[1:] for row in after} for record in records):
            raise StorageError("事务内8字段核对失败，撤销本次事务")
        connection.commit()
        log("batch_committed", table=table, before_count=len(current), after_count=len(after),
            inserted_count=len(missing), records_examined=len(records))
        return after, len(missing)
    except Exception:
        safe_rollback(connection, log)
        log("batch_rolled_back", table=table)
        raise


def temporary_transaction_test(connection, cursor, log):
    """只测临时表：合成测试记录不写 houseinfo、不写真实CSV。"""
    table = "part3_test_" + uuid.uuid4().hex
    definitions = ", ".join(f"`{field}` VARCHAR({length})" for field, length in zip(FIELDS, LIMITS))
    cursor.execute(f"CREATE TEMPORARY TABLE `{table}` (`id` INT AUTO_INCREMENT PRIMARY KEY, {definitions}) ENGINE=InnoDB CHARACTER SET utf8mb4")
    sample = ("事务测试'参数%s", "临时楼盘", "测试地址甲乙", "2室1厅1卫", "88.5㎡", "中层", "", "12000元/㎡")
    try:
        first, added = insert_batch(connection, cursor, [sample, sample], (), log, table)
        second, repeated = insert_batch(connection, cursor, [sample], first, log, table)
        if (added, repeated) != (1, 0) or tuple(second[0][1:]) != sample:
            raise StorageError("临时表提交、单位/空年代保留或去重测试失败")
        connection.begin()
        modified = ("仅用于回滚验证", *sample[1:])
        cursor.executemany(INSERT_SQL.replace("`houseinfo`", f"`{table}`"), [modified])
        connection.rollback()
        if snapshot(cursor, table) != second:
            raise StorageError("临时表rollback未还原事务")
        connection.rollback()
        result = {"scope": "session_temporary_table_only", "synthetic_test_data": True,
                  "commit_verified": True, "rollback_verified": True,
                  "exact_eight_fields_verified": True, "rerun_inserted_count": repeated,
                  "production_houseinfo_modified": False}
        log("temporary_transaction_test_passed", **result)
        return result
    finally:
        connection.rollback()
        cursor.execute(f"DROP TEMPORARY TABLE IF EXISTS `{table}`")
        connection.commit()


def dependency_summary():
    return {"part1": read_json(PART1), "part2": read_json(PART2), "csv_exists": CSV_PATH.is_file()}


def empty_status():
    return {"stage": 3, "state": "awaiting_csv", "checked_at": now(), "csv_sha256": None,
            "before_count": None, "after_count": None, "inserted_count": 0,
            "rerun_inserted_count": None, "samples_match": None,
            "actual_import_completed": False, "reason": "尚未执行真实入库"}


def safe_rollback(connection, log):
    if connection is not None:
        try:
            connection.rollback()
        except Exception as exc:
            log("rollback_failed", reason=f"{type(exc).__name__}: {exc}")


def operate(args, log):
    connection = None
    cursor = None
    advisory_locked = False
    status = empty_status()
    try:
        connection = connect()
        cursor = connection.cursor()
        log("connection_ok", host="mysql", port=3306, database="smartpark_lab", charset="utf8mb4", autocommit=False)
        schema = inspect_schema(cursor)
        atomic_json(BASE / "evidence" / f"schema_{args.command}.json", schema)
        log("schema_inspected", **schema)
        status.update(before_count=schema["row_count"], after_count=schema["row_count"])
        connection.rollback()
        if args.command == "check":
            test = temporary_transaction_test(connection, cursor, log)
            atomic_json(BASE / "evidence" / "temporary_transaction_test.json", test)
            atomic_json(BASE / "evidence" / "dependencies_check.json", dependency_summary())
        one, two, digest = dependencies()
        status["csv_sha256"] = digest
        if not schema["structure_ok"]:
            raise StorageError(schema.get("reason") or "; ".join(schema["issues"]))
        records, same_digest = read_csv()
        if digest != same_digest:
            raise StorageError("CSV在依赖核对与读取之间发生变化，停止入库")
        status["csv_rows"] = len(records)
        field_samples(records, (), two, args.cross_page_index)  # 写入前校验显式样本索引。
        if args.command == "check":
            status["reason"] = "表结构、第二阶段状态和CSV哈希校验通过；尚未执行run，未写真实房源"
            return status, 0
        # 事务前重新核对依赖，防止采集端更换CSV/状态。
        if dependencies()[2] != digest:
            raise StorageError("入库前CSV哈希变化，停止入库")
        cursor.execute("SELECT GET_LOCK(%s, %s)", ("smartpark_lab.houseinfo.part3_storage", 10))
        advisory_locked = cursor.fetchone()[0] == 1
        if not advisory_locked:
            raise StorageError("另一个第三阶段进程正在操作，未取得会话锁")
        cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        connection.commit()
        baseline = snapshot(cursor)
        connection.rollback()
        baseline_hash = fingerprint(baseline)
        if args.expected_db_fingerprint and baseline_hash != args.expected_db_fingerprint:
            raise StorageError("独立重跑前数据库出现未知变化，停止并保留现场")
        status.update(before_count=len(baseline), after_count=len(baseline), inserted_count=0)
        log("before_import", row_count=len(baseline), fingerprint=baseline_hash, csv_rows=len(records), csv_sha256=digest)
        checked, small_count = insert_batch(connection, cursor, records[:min(3, len(records))], baseline, log, expected_schema=schema["create_sql"])
        status.update(after_count=len(checked), inserted_count=small_count,
                      committed_batches=[{"phase": "small_real_sample", "inserted_count": small_count}])
        # 少量提交后立即回读全部8字段，核对通过才继续全量。
        if not all(row in {tuple(item[1:]) for item in checked} for row in records[:min(3, len(records))]):
            raise StorageError("少量真实记录8字段回读核验失败；已提交的小批数据保留")
        completed, bulk_count = insert_batch(connection, cursor, records, checked, log, expected_schema=schema["create_sql"])
        status.update(after_count=len(completed), inserted_count=small_count + bulk_count)
        status["committed_batches"].append({"phase": "all_csv", "inserted_count": bulk_count})
        validation = field_samples(records, completed, two, args.cross_page_index)
        atomic_json(BASE / "evidence" / f"samples_{args.command}.json", validation)
        if not validation["samples_match"]:
            raise StorageError("CSV/数据库逐字段核验失败")
        status.update(samples_match=True, final_db_fingerprint=fingerprint(completed),
                      cross_page_sample_verified=validation["cross_page_source_available"])
        # 使用新事务再读数据库，检查提交后是否有未知并发写入。
        fresh = snapshot(cursor)
        connection.rollback()
        if fresh != completed:
            raise StorageError("提交后数据库发生未知变化，停止自动验收并保留现场")
        status["actual_import_completed"] = True
        if args.command == "rerun":
            if status["inserted_count"] != 0:
                raise StorageError("独立重跑新增不为0，不能通过复跑验收")
            status.update(state="ready", rerun_inserted_count=0, reason="新进程独立重跑完成，新增0，CSV全部记录8字段核验一致")
            if not validation["cross_page_source_available"]:
                status.update(state="error", reason="独立重跑新增0，但缺少第二阶段跨页样本来源，三类样本验收未完成")
            atomic_json(BASE / "evidence" / "rerun_result.json", status)
        else:
            status["reason"] = "首次真实入库及逐字段核验完成，等待新进程独立重跑"
            atomic_json(BASE / "evidence" / "first_import_result.json", status)
        return status, 0 if status["state"] != "error" else 1
    except DependencyPending as exc:
        safe_rollback(connection, log)
        status.update(state=exc.state, reason=str(exc))
        log("dependency_not_ready", state=exc.state, reason=str(exc), real_import_attempted=False)
        return status, 2
    except Exception as exc:
        safe_rollback(connection, log)
        status.update(state="error", reason=f"{type(exc).__name__}: {exc}")
        log("operation_failed", reason=status["reason"], committed_inserted_count=status["inserted_count"])
        return status, 1
    finally:
        if cursor is not None:
            try:
                if advisory_locked:
                    cursor.execute("SELECT RELEASE_LOCK(%s)", ("smartpark_lab.houseinfo.part3_storage",))
            except Exception as exc:
                log("release_lock_failed", reason=str(exc))
            try:
                cursor.close()
            except Exception as exc:
                log("cursor_close_failed", reason=str(exc))
        if connection is not None:
            try:
                connection.close()
            except Exception as exc:
                log("connection_close_failed", reason=str(exc))
        log("resources_closed", connection_was_created=connection is not None, cursor_was_created=cursor is not None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "run", "rerun"))
    parser.add_argument("--cross-page-index", type=int, help="第二阶段确认的跨页样本0起始CSV索引；不可猜测")
    parser.add_argument("--expected-db-fingerprint", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    log = Log(args.command)
    log("started", command=args.command, csv_path=str(CSV_PATH), real_import=args.command != "check")
    status, code = operate(args, log)
    if args.command == "run" and code == 0:
        # operate 已退出并关闭连接；同一脚本以全新解释器和数据库连接重跑。
        command = [sys.executable, str(Path(__file__).resolve()), "rerun", "--expected-db-fingerprint", status["final_db_fingerprint"]]
        if args.cross_page_index is not None:
            command.extend(["--cross-page-index", str(args.cross_page_index)])
        try:
            child = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=180)
            (BASE / "logs" / f"rerun_process_{os.getpid()}.txt").write_text(child.stdout + child.stderr, encoding="utf-8")
            print(child.stdout, end="", flush=True)
            if child.returncode == 0:
                rerun = read_json(BASE / "evidence" / "rerun_result.json")
                if (not rerun or rerun["inserted_count"] != 0 or rerun["final_db_fingerprint"] != status["final_db_fingerprint"]
                        or rerun["csv_sha256"] != status["csv_sha256"]):
                    raise StorageError("独立重跑结果与首次入库不符")
                status.update(state="ready", rerun_inserted_count=0,
                              reason="真实CSV入库、8字段核验及新进程独立重跑新增0均已完成")
            else:
                status.update(state="error", reason=f"首次入库已完成，独立重跑失败，退出码{child.returncode}；已提交数据保留")
                code = 1
        except Exception as exc:
            status.update(state="error", reason=f"首次入库已提交；独立重跑异常 {type(exc).__name__}: {exc}；已提交数据保留")
            log("rerun_failed", reason=status["reason"], committed_inserted_count=status["inserted_count"])
            code = 1
        if code == 0 and not status.get("cross_page_sample_verified"):
            status.update(state="error", reason="真实入库已完成；缺少第二阶段跨页样本来源，不能宣称三类样本验收完成")
            code = 1
    status.update(checked_at=now(), log_file=str(log.path))
    atomic_json(BASE / "status.json", status)
    log("finished", **status)
    return code


if __name__ == "__main__":
    sys.exit(main())
