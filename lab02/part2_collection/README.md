# 房源采集与 CSV 核验

在课程容器中进入 `lab02` 后，可用本目录保存的 10 页网页复现 498 条 CSV。

```bash
python part2_collection/collect_houses.py trial --browser-manifest part2_collection/evidence/browser_full/manifest.json
python part2_collection/collect_houses.py collect --browser-manifest part2_collection/evidence/browser_full/manifest.json
python part2_collection/collect_houses.py verify
```

在线重新采集可运行 `python part2_collection/browser_collect.py`。浏览器输出保存在独立运行目录，标准 CSV 由上面的回放流程生成。[实验报告](REPORT_part2.md)
