# CSV 入库与结果核验

在课程容器的 `lab02` 目录运行：

```bash
python part3_storage/run_real_import.py
```

程序读取 [498 条标准 CSV](../data/houseinfo.csv)，先核对网页来源，再运行入库程序和独立重跑。相同八字段的记录会跳过。[实验报告](REPORT_part3.md) · [最新核验记录](evidence/real_pipeline_result.json)

[first8_result.ipynb](first8_result.ipynb) 是旧版的历史输出，其中 437 条的断言只适用于当时的数据库。
