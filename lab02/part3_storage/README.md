# 第三部分：CSV 入库与核对

本目录保留一套实际入库程序、报告和必要证据。当前材料对应前8页、437条CSV的历史结果；共享数据库后续可能已有498条，当前数量以实时查询为准。

| 文件或目录 | 用途 |
|---|---|
| [REPORT_part3.md](REPORT_part3.md) | 第三部分实验报告 |
| [run_real_import.py](run_real_import.py) | 真实CSV入库入口，包含来源检查和独立重跑 |
| [storage.py](storage.py) | 连接、参数化批量写入、事务与去重 |
| [first8_result.ipynb](first8_result.ipynb) | 已保存的前8页实际运行结果 |
| [status.json](status.json) | 该版本入库完成时的状态 |
| `images/` | 报告截图及用户提供的选择器、下一页证据 |
| `evidence/` | 首次入库、独立重跑、样本和结构核验 |
| `logs/` | 与正式入库对应的必要日志 |
| `browser_capture/` | 第二部分仍引用的真实网页来源，不能单独删除 |

在课程Jupyter终端的 `lab02` 目录运行：

```bash
python part3_storage/run_real_import.py
```

该命令读取 `data/houseinfo.csv`，不会重新采集网页。已有相同8字段的记录会被跳过，不清空数据库。`first8_result.ipynb` 保留当时数据库437条的输出与断言，供查看历史结果；后续共享数据库增加记录后，总数不再等于437。

缓存、重复HTML导出、旧失败Notebook、旧测试输出和未引用的重复日志已经清理。保留的正式记录与CSV来源关系未改变。
