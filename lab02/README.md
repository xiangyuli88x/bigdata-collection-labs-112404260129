# 实验二 · 房源采集与 MySQL 存储

实验流程为网页采集、CSV 去重、读取到 Python 内存、写入 MySQL，再用新进程重跑核验。

[查看实验二总报告](REPORT.md)

| 项目 | 当前结果 |
|---|---:|
| 采集范围 | 第 1 至第 10 页，已到末页 |
| 原始记录 | 600 |
| 重复记录 | 102 |
| CSV 数据行数 | 498 |
| MySQL 核验总数 | 498 |
| 独立重跑新增 | 0 |

- 第一部分准备 MySQL 环境和表结构。[环境与建表报告](part1_mysql/REPORT_part1.md)
- 第二部分解析网页、确认分页并生成 CSV。[采集报告](part2_collection/REPORT_part2.md) · [运行说明](part2_collection/README.md) · [CSV](data/houseinfo.csv)
- 第三部分核验来源后批量入库并独立重跑。[入库报告](part3_storage/REPORT_part3.md) · [运行说明](part3_storage/README.md)

使用课程根目录的 `start-course.bat` 和 `start-mysql.bat` 启动环境。在 JupyterLab 的 Terminal 中运行：

```bash
cd /home/pwuser/workspace/bigdata-collection-labs-112404260129/lab02
python part2_collection/collect_houses.py verify
python part3_storage/run_real_import.py
```

第一部分保留建表时的历史记录。最新数据和核验结果以第二、第三部分的报告为准。
