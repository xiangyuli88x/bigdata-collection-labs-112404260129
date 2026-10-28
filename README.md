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

本目录当前保存的是**前8页版本：480条原始记录，按8字段完全相同去重后为437条**。数据文件为 [`lab02/data/houseinfo.csv`](lab02/data/houseinfo.csv)。这里的历史报告和截图对应437条，不代表后来完成的10页498条版本。

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

