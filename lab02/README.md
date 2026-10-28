# 实验二：房源采集与 MySQL 存储

本文件是实验二的使用说明与目录导航。实验流程为：**房源网页 → 解析8个字段 → 去重保存CSV → 写入MySQL → 重跑与样本核对**。

说明更新日期：2026年10月28日。

## 当前数据版本

本目录保留的是前8页实验版本，程序、CSV和三部分历史报告应按这个范围理解。

| 项目 | 本目录保存的结果 |
|---|---:|
| 页面范围 | 前8页 |
| 去重前记录数 | 480条 |
| 完全相同的重复记录数 | 43条 |
| CSV数据行数，不含表头 | 437条 |
| 该版本首次入库记录数 | 437条 |
| 当时独立重跑新增 | 0条 |
| 是否到达教学站末页 | 否，第8页仍有下一页 |

后续另有10页、498条的完整版本，本目录的437条CSV、旧报告和截图尚未同步为该版本。这里的“437条入库”是当时的运行结果；共享课程数据库后来可能已有更多记录，当前总数应以实时查询为准。

## 先看哪些文件

| 目的 | 文件 |
|---|---|
| 第一部分报告 | [part1_mysql/REPORT_part1.md](part1_mysql/REPORT_part1.md) |
| 表结构SQL | [part1_mysql/setup.sql](part1_mysql/setup.sql) |
| 第一部分已保存的核验Notebook | [part1_mysql/verification.ipynb](part1_mysql/verification.ipynb) |
| 第二部分报告 | [part2_collection/REPORT_part2.md](part2_collection/REPORT_part2.md) |
| 第二部分运行说明 | [part2_collection/README.md](part2_collection/README.md) |
| 浏览器采集入口 | [part2_collection/browser_collect.py](part2_collection/browser_collect.py) |
| 解析、分页及CSV来源核验 | [part2_collection/collect_houses.py](part2_collection/collect_houses.py) |
| 已保存的标准CSV | [data/houseinfo.csv](data/houseinfo.csv) |
| 第三部分报告 | [part3_storage/REPORT_part3.md](part3_storage/REPORT_part3.md) |
| 真实CSV入库入口 | [part3_storage/run_real_import.py](part3_storage/run_real_import.py) |
| 入库、事务及去重实现 | [part3_storage/storage.py](part3_storage/storage.py) |
| 前8页入库结果Notebook | [part3_storage/first8_result.ipynb](part3_storage/first8_result.ipynb) |

根目录的 `anjuke.py`、`environment_check.py` 和 `tools/` 保留了早期配套实现。查看及复跑本次三阶段流程时，优先使用上表中各阶段的入口；不要把不同版本的入口、CSV和报告混用。

## 文件夹作用

```text
lab02/
  README.md                 本使用说明
  data/houseinfo.csv        当前437条标准数据
  part1_mysql/             环境检查、建表SQL、第一部分报告
    images/                实际操作截图
    evidence/              原始检查与查询记录
  part2_collection/        浏览器采集、解析、分页、CSV核验
    images/                实际操作截图
    evidence/              网页、来源清单和采集日志
  part3_storage/           CSV入库、事务、去重和样本核对
    images/                实际操作截图
    evidence/              入库与独立重跑结果
    logs/                  程序运行日志
  evidence/                其他历史记录
  tools/                   配套生成工具
```

`REPORT_part*.md` 是实验报告，`README.md` 是运行说明；`status.json` 是对应程序最后保存的状态，不能代替实时数据库查询，也不能仅凭文件名判断是哪一版结果。

## 运行前准备

1. 在Windows打开Docker Desktop，等待引擎就绪。
2. 在课程根目录 `D:\大数据采集与处理-学生实验环境` 使用 `start-course.bat`、`start-mysql.bat` 启动原课程环境和教学数据库。
3. 打开课程JupyterLab，在 **Terminal** 中输入下面的命令。这里是Linux终端，不是在Windows的CMD中输入。

```bash
cd /home/pwuser/workspace/bigdata-collection-labs-112404260129/lab02
pwd
```

`pwd` 应显示与上面一致的 `lab02` 目录。每条命令单独按回车，前面不要复制 `$`，末尾不要加反斜杠 `\`。如果出现续行提示符 `>`，先按 **Ctrl+C** 再重新输入。

## 第一部分：查看环境和表结构

首先阅读第一部分报告和已保存的核验Notebook。若只想查看当前数据库，可双击课程根目录的 `mysql-console.bat`，按提示输入教学密码，再执行：

```sql
USE smartpark_lab;
SHOW TABLES;
DESCRIBE houseinfo;
SELECT COUNT(*) AS current_count FROM houseinfo;
```

这些查询不改变房源记录。第一部分保存的 `before_count=0` 是首次准备时的历史基线，不能把后续查询的总数改写成当时的结果。

## 第二部分：查看CSV或重新采集

在上述Jupyter终端的 `lab02` 目录中核验现有CSV、网页来源及样本：

```bash
python part2_collection/collect_houses.py verify
```

如需重新采集前8页，运行独立浏览器入口：

```bash
python part2_collection/browser_collect.py
```

也可在Windows双击 `part2_collection/运行浏览器采集.bat`。浏览器程序每次结果另存到 `part2_collection/evidence/browser_runs/日期时间_编号/`，包括HTML、CSV、来源清单、日志和截图；它不会自动替换 `data/houseinfo.csv` 或直接写入MySQL。

`part2_collection/browser_last_run.json` 记录最新一次独立浏览器运行结果。网站出现访问验证、重复页面或结构异常时应保留失败原因，不把异常停止写成采集完整。

## 第三部分：读取CSV并入库核对

先阅读第三部分报告和 `first8_result.ipynb`。确需重新执行这份437条CSV的入库时，在 `lab02` 目录运行：

```bash
python part3_storage/run_real_import.py
```

程序先核对第二部分状态、CSV哈希和真实网页来源，再通过PyMySQL批量入库，最后启动新进程检查重复运行。此命令会连接并可能写入数据库，不重新采集网页。相同8字段的已有房源不会再次插入，也不通过清空表来实现重跑。

如果当前共享数据库已包含后来的498条记录，重跑这份437条CSV后数据库总数不应被要求降回437；应检查本次新增是否为0，并按当次实际输出记录结果。

## 连接参数与字段顺序

Python应在课程容器中运行：`host="mysql"`、`port=3306`、`database="smartpark_lab"`、`user="student"`、教学密码 `123456`、`charset="utf8mb4"`。MySQL未向Windows发布端口，容器中使用服务名 `mysql` 连接。

CSV固定8字段顺序：

```text
title,house,address,struct,area,floor,maketime,price
```

面积、单价保留原单位；建造年代缺失时允许空字符串。使用参数化INSERT、事务提交与回滚，并在结束时关闭游标和连接。

## 提交到GitHub时如何保持清楚

仓库首页保留 `README.md`、`lab01/`、`lab02/` 并列即可。老师先从仓库首页进入本使用说明，再阅读三份报告，不必逐个寻找过程文件。

- 保留CSV、实际使用的程序、三份报告、报告引用的截图和必要来源证据。
- `.git` 是本地仓库元数据，不是实验材料；缓存目录、重复备份和无关下载物不作为作业上传。
- 网页上传文件多时分批进行，保留 `lab02/part1_mysql/...`、`lab02/part2_collection/...` 等层级；文件很多的 `evidence/` 可继续拆分批次。
- 上传后打开本使用说明和三份报告，确认相对链接和图片能显示。
- 提交498条完整版前，应同时更新本目录的CSV、来源清单、状态、报告和对应结果截图，不能只改README中的条数。

网页上传方法见 [GitHub官方说明](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository)。
