"""在课程容器中生成并实际执行核验 Notebook，不伪造输出。"""
from pathlib import Path

import nbformat
from nbclient import NotebookClient

BASE = Path(__file__).resolve().parent
cells = [
    nbformat.v4.new_markdown_cell('# 第一阶段 MySQL 实测核验\n\n文件：`part1_mysql/verification.ipynb`。环境由父聊天配置，本次只读复用；本 Notebook 不写入房源。'),
    nbformat.v4.new_code_cell('''import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from IPython.display import display
import pandas as pd
from check_mysql import connect_mysql

environment = json.loads(Path("evidence/environment.json").read_text(encoding="utf-8"))
print("Environment evidence:", environment["checked_at"])
print("Docker Engine:", environment["docker_engine_version"])
for label in ("workspace", "mysql"):
    item = environment[label]
    print(item["name"], "running=", item["running"], "health=", item["health"])
print("Jupyter HTTP:", environment["jupyter"]["status_code"])
print("MySQL published ports:", environment["mysql"]["published_ports"])
print("L05 volume:", environment["volume"]["name"])
for mount in environment["workspace"]["mounts"]:
    if mount["Destination"] == "/home/pwuser/workspace":
        print("Bind:", mount["Source"], "->", mount["Destination"])
for line in environment["teaching_helper"]["output"]:
    print(line)
print("environment_ok:", environment["environment_ok"])'''),
    nbformat.v4.new_code_cell('''def show_query(sql):
    print("SQL:", sql)
    with connect_mysql() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            if cursor.description:
                display(pd.DataFrame(cursor.fetchall(), columns=[item[0] for item in cursor.description]))
            else:
                print("OK")

print("Live MySQL query:", datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"))
show_query("SELECT VERSION() AS version, DATABASE() AS database_name, CURRENT_USER() AS account_name")
show_query("SHOW DATABASES")
show_query("USE smartpark_lab")
show_query("SHOW TABLES")'''),
    nbformat.v4.new_code_cell('''print("Live table check:", datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"))
show_query("DESCRIBE houseinfo")
show_query("SELECT COUNT(*) AS before_count FROM houseinfo")
show_query("SELECT TABLE_COLLATION, ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA='smartpark_lab' AND TABLE_NAME='houseinfo'")'''),
    nbformat.v4.new_code_cell('''# 独立重跑安全建表检查：已有表时只查询，保存独立证据。
import contextlib
import io
from check_mysql import run
with contextlib.redirect_stdout(io.StringIO()):
    repeat = run()
print("Recheck:", repeat["checked_at"])
for key in ("state", "version", "current_user", "table_existed_before", "created_table", "schema_ok", "before_count", "record_writes"):
    print(key, "=", repeat.get(key))
assert repeat["state"] == "ready"
assert repeat["created_table"] is False
assert repeat["record_writes"] == 0
print("Existing-table recheck passed; no house record was written.")'''),
]
notebook = nbformat.v4.new_notebook(cells=cells, metadata={'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'}, 'language_info': {'name': 'python'}})
target = BASE / 'verification.ipynb'
nbformat.write(notebook, target)
NotebookClient(notebook, timeout=90, kernel_name='python3', resources={'metadata': {'path': str(BASE)}}).execute()
nbformat.write(notebook, target)
print('EXECUTED:', target)
print('Code cells:', sum(cell.cell_type == 'code' for cell in notebook.cells))
print('Errors:', sum(output.output_type == 'error' for cell in notebook.cells if cell.cell_type == 'code' for output in cell.outputs))
