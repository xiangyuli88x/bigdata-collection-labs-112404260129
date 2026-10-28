# 第二部分：浏览器采集与CSV保存

## 直接运行

双击本文件夹中的 **运行浏览器采集.bat**。脚本会使用已经运行的课程容器，在容器内启动独立 Chromium 浏览器，最多读取教学站前8页。浏览器在后台运行，命令窗口会显示逐页进度。

也可以在 JupyterLab 中进入本文件夹、打开 Terminal，运行：

```bash
python browser_collect.py
```

此前已在课程容器中实际验证：脚本独立启动浏览器、按真实下一页链接取得8页，共480条，完全相同的重复记录43条，去重后CSV为437条。当前只保留标准CSV所需的一套来源；重复运行副本已清理。后续浏览器采集和解析核验统一放在 `evidence/runs/`，通过 `browser_` 前缀区分新的浏览器运行。

## 脚本做什么

1. Selenium启动Chrome/Chromium并打开教学站。
2. 等待房源字段完整，读取真实页面HTML。
3. 按 `div.property` 分条解析8字段；读取“下一页”的href并补全地址。
4. 每页间隔至少1秒，最多保存8页。验证页、缺失字段、重复页面或越站链接会停止运行。
5. 保存完整HTML、第一页和最后一页截图、来源清单、运行日志。
6. 按8字段完全相同去重，保存UTF-8-SIG编码CSV并重新读取核对。

第8页仍有下一页时，程序明确记为“按要求保存前8页”，不宣称到达站点末页。

## 结果在哪里

每次运行单独保存到：

```text
evidence/runs/browser_日期时间_编号/
  page_001.html ... page_008.html
  page_001.png
  page_008.png
  manifest.json
  houseinfo.csv
  run.jsonl
  result.json
```

下次运行时会生成 `browser_last_run.json`，记录该次浏览器脚本的结果。遇到错误时保存 `failure_page.html`、`failure_page.png` 及实际错误原因，不生成空CSV或把失败写成完成。

新结果保存在独立文件夹，已有 `lab02/data/houseinfo.csv`、第二部分 `status.json` 和 MySQL数据保持不变。本脚本只采集和保存，不入库。

## 文件作用

- `browser_collect.py`：新增的独立浏览器采集入口，包含启动浏览器、翻页和HTML保存逻辑。
- `collect_houses.py`：已有的字段解析、CSV保存和来源核验模块；浏览器入口复用它的解析函数，两个文件应放在一起。
- `test_browser_collect.py`：验证页立即停止、8页上限及实际网页记录CSV回读检查。
- `运行浏览器采集.bat`：Windows双击入口，调用当前课程容器；需要Docker和课程环境已经启动。
- `REPORT_part2.md`：第二部分实验报告。

## 与已有入库流程衔接

如需把新采集结果转成标准 `lab02/data/houseinfo.csv`，使用现有 `collect_houses.py` 的 `trial`、`collect`、`verify` 命令，三者指向本次生成的真实 `manifest.json`；`collect` 加 `--take-pages 8`。直接运行新浏览器脚本不会替换标准CSV。

现有标准CSV已对应437条入库记录，本次无需重复导入。`status.json` 表示标准CSV的验收状态，与新脚本的独立运行结果区分。

## 依赖与方法依据

已验证环境为课程容器中的 Selenium 4.27.1、Chromium/Chrome for Testing及现有ChromeDriver缓存，无需重新安装课程环境。Windows系统Python不是本次验证的运行环境。

实现依据：[Selenium浏览器选项](https://www.selenium.dev/documentation/webdriver/drivers/options/)、[页面等待策略](https://www.selenium.dev/documentation/webdriver/waits/)、[Selenium Manager驱动管理](https://www.selenium.dev/documentation/selenium_manager/)。没有加入验证码识别、Cookie复制或隐藏自动化标记等处理。
