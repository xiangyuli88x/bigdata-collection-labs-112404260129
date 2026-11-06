# 大数据采集与处理实验

- 姓名：李翔宇
- 学号：112404260129
- 班级：数据1241

## Lab 1

实验一完成 Device JSON API 分页采集、Company 静态 HTML 解析、分页验证和结果保存。

详见 [`lab01/REPORT.md`](lab01/REPORT.md)。

## Lab 2

实验二完成房源网页解析、分页采集、CSV保存及MySQL存储，按三个阶段分别保存程序、报告和实际运行证据。

**使用说明与文件导航：[`lab02/README.md`](lab02/README.md)。**

| 阶段 | 内容 | 实验报告 |
|---|---|---|
| 第一部分 | Docker/MySQL环境、账号与房源表结构 | [环境与建表](lab02/part1_mysql/REPORT_part1.md) |
| 第二部分 | 房源解析、分页与CSV保存 | [房源采集与CSV](lab02/part2_collection/REPORT_part2.md) |
| 第三部分 | CSV批量入库、事务、去重及结果核对 | [MySQL存储](lab02/part3_storage/REPORT_part3.md) |

实验二已采集到第 10 页末页，共 600 条原始房源。按 8 个字段完全相同去重后，得到 **498 条**记录。MySQL 已核验全部 498 条记录，独立重跑新增 0 条。数据见 [houseinfo.csv](lab02/data/houseinfo.csv)，核验结果见 [入库报告](lab02/part3_storage/REPORT_part3.md)。

## 目录结构

```text
README.md                 仓库首页与实验入口
lab01/                    实验一
lab02/                    实验二
  README.md               实验二使用说明
  data/                   CSV数据
  part1_mysql/            第一部分程序、报告和证据
  part2_collection/       第二部分程序、报告和证据
  part3_storage/          第三部分程序、报告和证据
```

