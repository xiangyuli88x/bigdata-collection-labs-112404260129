"""只读验收交付文件，写本目录的文件清单并原子更新状态证据路径。"""
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import nbformat

from check_mysql import atomic_json

BASE = Path(__file__).resolve().parent


def jpeg_size(content):
    """用标准库读取 JPEG SOF 尺寸；不安装依赖，不转换或编辑截图。"""
    assert content[:2] == b'\xff\xd8' and content[-2:] == b'\xff\xd9'
    index = 2
    while index < len(content):
        assert content[index] == 0xFF
        while content[index] == 0xFF:
            index += 1
        marker = content[index]
        index += 1
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            continue
        length = int.from_bytes(content[index:index + 2], 'big')
        assert length >= 2
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            height = int.from_bytes(content[index + 3:index + 5], 'big')
            width = int.from_bytes(content[index + 5:index + 7], 'big')
            return width, height
        index += length
    raise ValueError('JPEG SOF not found')


status = json.loads((BASE / 'status.json').read_text(encoding='utf-8'))
assert status['stage'] == 1 and status['state'] == 'ready'
assert status['schema_ok'] is True
assert status['version'] == '8.4.11'
assert status['before_count'] == 0 and status['record_writes'] == 0
notebook = nbformat.read(BASE / 'verification.ipynb', as_version=4)
code_cells = [cell for cell in notebook.cells if cell.cell_type == 'code']
assert len(code_cells) == 4 and all(cell.execution_count for cell in code_cells)
assert not any(output.output_type == 'error' for cell in code_cells for output in cell.outputs)
images = []
for path in sorted(path for path in (BASE / 'images').iterdir() if path.suffix.lower() in ('.jpg', '.png')):
    content = path.read_bytes()
    if path.suffix.lower() == '.png':
        assert content.startswith(b'\x89PNG\r\n\x1a\n')
        assert content[12:16] == b'IHDR'
        width = int.from_bytes(content[16:20], 'big')
        height = int.from_bytes(content[20:24], 'big')
    else:
        width, height = jpeg_size(content)
    assert width >= 1000 and height >= 600
    images.append({'file': path.relative_to(BASE).as_posix(), 'width': width, 'height': height, 'sha256': hashlib.sha256(content).hexdigest()})
assert {'images/01_environment.jpg', 'images/02_mysql_queries.jpg', 'images/03_schema_count.jpg', 'images/04_safe_recheck.jpg'}.issubset(item['file'] for item in images)
manual_path = BASE / 'evidence/user_screenshots.json'
manual = json.loads(manual_path.read_text(encoding='utf-8')) if manual_path.exists() else None
if manual is not None:
    by_path = {item['file']: item for item in images}
    for item in manual['files']:
        assert item['file'] in by_path
        assert item['sha256'] == by_path[item['file']]['sha256']
report = (BASE / 'REPORT_part1.md').read_text(encoding='utf-8')
for relative in re.findall(r'\]\(([^)]+)\)', report):
    if not relative.startswith(('http:', 'https:')):
        assert (BASE / relative).is_file(), f'Broken report link: {relative}'
snapshot = {
    'checked_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),
    'state': 'pass', 'notebook_code_cells': 4, 'notebook_errors': 0,
    'report_links_ok': True, 'images': images,
    'manual_screenshot_review': manual,
    'note': '文件验收；数据库基线时间保持为 status.checked_at，不冒充重新查库。',
}
atomic_json(BASE / 'evidence/package_validation.json', snapshot)
status['evidence_files'] = sorted({
    *(path.relative_to(BASE).as_posix() for path in (BASE / 'evidence').iterdir() if path.is_file()),
    *(item['file'] for item in images), 'verification.ipynb',
})
status['report_file'] = 'REPORT_part1.md'
status['package_checked_at'] = snapshot['checked_at']
status['manual_startup_screenshot_completed'] = bool(manual and manual['mysql_startup_success_visible'])
status['manual_mysql_console_screenshot_completed'] = bool(manual and manual['mysql_console_visible'])
status['manual_terminal_count_screenshot_completed'] = bool(manual and manual['terminal_count_result_visible'])
status['manual_terminal_current_count'] = manual.get('terminal_current_count') if manual else None
status['exact_before_count_zero_terminal_screenshot_completed'] = bool(manual and manual.get('exact_before_count_zero_terminal_screenshot_completed', False))
status['manual_start_course_screenshot_completed'] = bool(manual and manual['start_course_process_visible'])
status['manual_screenshot_pending'] = manual['pending'] if manual else ['Manual terminal screenshots not provided.']
status['screenshots_kind'] = 'Actual JupyterLab screenshots plus user-provided original Windows terminal screenshots; raw mysql CLI transcript provided separately.'
atomic_json(BASE / 'status.json', status)
print(json.dumps(snapshot, ensure_ascii=False, indent=2))
print('STATUS_READY:', status['checked_at'], status['before_count'], status['schema_ok'])
