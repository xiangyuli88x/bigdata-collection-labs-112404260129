"""在课程容器内执行；只在表不存在时建表，绝不插入或清空房源记录。"""
from __future__ import annotations

import json
import os
import platform
import sys
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pymysql

BASE = Path(__file__).resolve().parent
EVIDENCE = BASE / 'evidence'
EXPECTED = [
    ('id', 'int', 'NO', 'PRI', None, 'auto_increment', '自增长主键'),
    ('title', 'varchar(200)', 'YES', '', None, '', '标题'),
    ('house', 'varchar(50)', 'YES', '', None, '', '楼盘'),
    ('address', 'varchar(200)', 'YES', '', None, '', '地址'),
    ('struct', 'varchar(50)', 'YES', '', None, '', '户型'),
    ('area', 'varchar(20)', 'YES', '', None, '', '建筑面积'),
    ('floor', 'varchar(20)', 'YES', '', None, '', '楼层'),
    ('maketime', 'varchar(20)', 'YES', '', None, '', '建造年代'),
    ('price', 'varchar(20)', 'YES', '', None, '', '每平方米单价'),
]


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def connect_mysql():
    """统一课程连接参数；调用者负责关闭连接。"""
    return pymysql.connect(host='mysql', port=3306, database='smartpark_lab', user='student', password='123456', charset='utf8mb4', autocommit=False, connect_timeout=5, read_timeout=10, write_timeout=10)


def run() -> dict:
    EVIDENCE.mkdir(exist_ok=True)
    checked = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
    run_id = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d_%H%M%S_%f')
    report = {
        'stage': 1, 'state': 'error', 'checked_at': checked,
        'version': None, 'database': 'smartpark_lab', 'table': 'houseinfo',
        'before_count': None, 'schema_ok': False, 'queries': [], 'warnings': [],
        'python_version': platform.python_version(), 'python_executable': sys.executable,
        'created_table': False, 'record_writes': 0,
        'connection': {'host': 'mysql', 'port': 3306, 'user': 'student', 'database': 'smartpark_lab', 'charset': 'utf8mb4'},
    }
    transcript = [f'check_mysql.py | {checked}', 'Record writes: 0 (no CSV read, no INSERT/UPDATE/DELETE)']
    connection = None
    try:
        environment = json.loads((EVIDENCE / 'environment.json').read_text(encoding='utf-8-sig'))
        report['environment_checked_at'] = environment['checked_at']
        report['environment_ok'] = environment['environment_ok']
        if not environment['environment_ok']:
            raise RuntimeError('环境核验未通过；停止建表。')
        age = (datetime.now(ZoneInfo('Asia/Shanghai')) - datetime.fromisoformat(environment['checked_at'])).total_seconds()
        if not 0 <= age <= 900:
            raise RuntimeError('环境证据已超过15分钟或时间异常；请先重跑 check_environment.ps1。')
        if environment['teaching_helper']['exit_code'] != 0:
            report['warnings'].append('教学 l05-mysql.ps1 -Action Check 失败，详见 environment.json；运行时环境、账号和表结构另行实测。')
        connection = connect_mysql()
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            def query(sql, params=None):
                cursor.execute(sql, params)
                rows = cursor.fetchall() if cursor.description else []
                report['queries'].append({'sql': sql, 'params': params, 'rows': rows})
                transcript.extend(['', '> ' + sql, json.dumps(rows, ensure_ascii=False, indent=2, default=str)])
                return rows

            identity = query('SELECT VERSION() AS version, DATABASE() AS database_name, CURRENT_USER() AS account_name, USER() AS connection_user, @@character_set_connection AS connection_charset')[0]
            report.update(version=identity['version'], current_user=identity['account_name'], connection_user=identity['connection_user'], connection_charset=identity['connection_charset'])
            if identity['database_name'] != 'smartpark_lab' or identity['account_name'] != 'student@%':
                raise RuntimeError('连接数据库或账号与课程要求不符。')
            report['databases'] = query('SHOW DATABASES')
            query('USE smartpark_lab')
            tables_before = query('SHOW TABLES')
            report['tables_before'] = [next(iter(row.values())) for row in tables_before]
            report['table_existed_before'] = 'houseinfo' in report['tables_before']
            if not report['table_existed_before']:
                setup = (BASE / 'setup.sql').read_text(encoding='utf-8')
                start = setup.index('CREATE TABLE IF NOT EXISTS houseinfo (')
                end = setup.index(';', start)
                query(setup[start:end])
                report['created_table'] = True
            tables_after = query('SHOW TABLES')
            report['tables_after'] = [next(iter(row.values())) for row in tables_after]
            report['describe'] = query('DESCRIBE houseinfo')
            full_columns = query('SHOW FULL COLUMNS FROM houseinfo')
            table_info = query("SELECT TABLE_COLLATION, ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s", ('smartpark_lab', 'houseinfo'))[0]
            report['table_info'] = table_info
            report['show_create_table'] = query('SHOW CREATE TABLE houseinfo')
            report['before_count'] = int(query('SELECT COUNT(*) AS before_count FROM houseinfo')[0]['before_count'])
            differences = []
            if len(full_columns) != len(EXPECTED):
                differences.append(f'列数应为9，实际为{len(full_columns)}')
            keys = ('Field', 'Type', 'Null', 'Key', 'Default', 'Extra', 'Comment')
            for index, (actual, expected) in enumerate(zip(full_columns, EXPECTED), 1):
                for key, wanted in zip(keys, expected):
                    if actual[key] != wanted:
                        differences.append(f'第{index}列 {key}: expected={wanted!r}, actual={actual[key]!r}')
                if index > 1 and not str(actual['Collation']).startswith('utf8mb4_'):
                    differences.append(f'第{index}列不是 utf8mb4')
            if not table_info['TABLE_COLLATION'].startswith('utf8mb4_'):
                differences.append('表字符集不是 utf8mb4')
            report['schema_differences'] = differences
            report['schema_ok'] = not differences
            if differences:
                raise RuntimeError('已有表结构不符合手册；未执行 ALTER 或删除，差异已记录。')
            report['state'] = 'ready'
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
        transcript.append('ERROR: ' + report['error'])
    finally:
        if connection is not None:
            connection.close()
    transcript.extend(['', f"state={report['state']} schema_ok={report['schema_ok']} before_count={report['before_count']}", 'Only missing-table CREATE was allowed. Record writes: 0.'])
    json_name = f'evidence/mysql_{run_id}.json'
    log_name = f'evidence/mysql_{run_id}.txt'
    report['evidence_files'] = ['evidence/environment.json', json_name, log_name]
    atomic_json(BASE / json_name, report)
    (BASE / log_name).write_text('\n'.join(transcript) + '\n', encoding='utf-8')
    atomic_json(BASE / 'status.json', report)
    print('\n'.join(transcript))
    print('STATUS_FILE:', BASE / 'status.json')
    return report


if __name__ == '__main__':
    result = run()
    raise SystemExit(0 if result['state'] == 'ready' else 1)
