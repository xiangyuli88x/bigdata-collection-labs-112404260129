# 实验二第二阶段报告：房源采集与 CSV

## 最新结果：按用户要求保存前8页（2026-10-27 16:59）

已按用户明确要求在第8页收尾。正常浏览器加载后保存了8页真实DOM快照，每页60条，共480条；按8字段完全相同去重43条，最终 [houseinfo.csv](../data/houseinfo.csv) 含437条。已实际执行两页试采、前8页回放保存和CSV验收，来源链、哈希及首条/跨页/所保存范围末条样本均核对通过。

来源为 `browser_snapshot`，记录于[真实浏览器DOM清单](../part3_storage/browser_capture/20261027T163224/manifest.json)。当前状态 `ready` 表示用户指定的前8页CSV已验收，`scope_complete=true`；第8页仍有下一页，因此保留 `complete=false`，不声明到达站点末页。

CSV SHA256：`e4d5bbecab33daaba1c81118123f23f77e73361a4696ef9862f9284d19a87d87`。

**下文保留15:34的requests验证页阻断与早期程序检查历史；其中“未生成CSV”等结论属于当时记录，当前结果以上述前8页验收为准。**

- 班级：
- 姓名：
- 学号：
- 实验日期：2026年10月27日
- 源码：`collect_houses.py`
- 数据来源：在线教学站 `http://www.bspider.top/anjuke/`
- 教师网页快照：当前无文件，未使用。
- 本阶段结论：**来源受阻，未完成房源采集，未生成标准 CSV。**

## 本次实际运行

在已运行的课程容器 `smartpark-student-course-workspace-1` 内执行 Python，没有重建课程环境。实际 Python 为3.12.3，requests 为2.34.2，BeautifulSoup 为4.15.0。本阶段没有操作数据库，也没有修改根目录 `anjuke.py`、`environment_check.py` 或实验一文件。

2026年10月27日15:34:38（北京时间）执行：

```bash
cd /home/pwuser/workspace/bigdata-collection-labs-112404260129/lab02/part2_collection
python collect_houses.py trial
```

实际事件日志见 [run.json](evidence/runs/20261027T153438_086898_42c6f6de/run.json)：

```text
15:34:38  请求教学站，第1页，http://www.bspider.top/anjuke/
15:34:41  本次运行失败并停止，state=blocked_source
           教学站返回访问验证页，停止自动采集
```

| 核对项 | 实际结果 |
|---|---|
| HTTP状态码 | 200 |
| 网页标题 | 访问验证-安居客 ws:3703571468 |
| `div.property` 匹配数 | 0 |
| 成功解析房源页数 | 0 |
| 原始记录数 / 去重后记录数 | 0 / 0 |
| 标准 `data/houseinfo.csv` | 未生成 |
| `status.json` | `blocked_source`，`complete=false` |
| 终止原因 | 首页为访问验证页，立即停止自动采集 |

HTTP 200 说明服务器返回了页面，页面内容仍需检查。本次真实响应标题及正文均表明是访问验证，不能作为房源数据解析。

本次仅请求了首页，没有尝试绕过验证，没有请求真实安居客，也没有继续请求第二页。没有使用参考 CSV 或生成房源样例来替代实际采集。

## 真实响应与来源证据

- [原始响应字节](evidence/runs/20261027T153438_086898_42c6f6de/page_001_hop_0.bin)
- [按响应编码保存的HTML](evidence/runs/20261027T153438_086898_42c6f6de/page_001_hop_0.html)
- [响应诊断与哈希](evidence/runs/20261027T153438_086898_42c6f6de/page_001_hop_0.json)
- [运行日志及异常详情](evidence/runs/20261027T153438_086898_42c6f6de/run.json)
- [保护逻辑实际检查结果](evidence/safety_checks.json)
- [浏览器工具尝试记录](evidence/browser_attempt.json)

原始响应与保存HTML的 SHA256 均为：

```text
216c25da22480d49c0e36148302e1dcc845620ee04ae22feb63a1dd194195b27
```

程序分别保存原始字节与UTF-8解码页面，并核对两者各自的哈希及解码对应关系。本次响应编码为UTF-8，两份文件的字节一致；不能把重新编码文件与另一份原始响应的哈希混用。

## 网页分析与8字段解析

### 选择器来源及浏览器步骤

本次未取得房源列表 DOM，以下选择器依据实验手册和现有根脚本的只读参考实现，**未在当前房源网页上核对**。

| 报告要求 | 本次情况 |
|---|---|
| F12 → Elements → Copy selector | 未完成 |
| 复制的原始标题选择器 | 未取得 |
| 房源父容器现场高亮与第二条对照 | 未完成 |
| `div.property` 的实际匹配 | 当前验证页中为0 |
| 标题、面积、单价的真实HTML节点 | 当前未取得 |
| 首条、第二条、末条逐字段对照 | 未完成 |

浏览器工具的创建标签操作超时，随后电脑操作工具因无法可靠确认当前浏览器网址而停止。该工具问题只说明浏览器操作没有完成；网站受阻结论来自课程容器保存的实际HTTP响应。未制作模拟网页或替代截图。

### 代码已实现的解析规则

8字段固定顺序为：

```text
title,house,address,struct,area,floor,maketime,price
```

| 字段 | 代码定位与处理 | 当前验证状态 |
|---|---|---|
| title | 房源内 `.property-content-title-name`、`.property-content-title h3`、`h3` | 待真实房源页核对 |
| house | `.property-content-info-comm-name` | 待真实房源页核对 |
| address | `.property-content-info-comm-address`；`get_text(strip=True)` | 待真实房源页核对 |
| struct | `.property-content-info-text` 中按“室/厅/卫”语义识别 | 待真实房源页核对 |
| area | 属性项中识别面积单位，保留完整属性文字 | 待真实房源页核对 |
| floor | 按“楼层/共N层/高、中、低层”等语义识别 | 待真实房源页核对 |
| maketime | 属性项中查找年份，缺失返回空字符串 | 待真实房源页核对 |
| price | `.property-price-average`；要求每平方米单价单位 | 待真实房源页核对 |

`select()` 取得一页中所有房源及一条房源中的属性项；`select_one()` 取得单条房源里的具体字段。地址取值不向相邻子标签额外插入空格。楼层按语义查找，避免把朝向当成楼层；单价独立定位并核对单位，不使用万元总价兜底。必要字段不明确时停止并保存错误，不静默丢弃记录。

代码位置：`parse_page()`、`node_text()`、`parse_record()`。真实验证页识别已实际回放通过，房源字段解析仍未验证。

**本项截图：未完成。** 没有房源页面可供字段对照，浏览器操作也未完成，不能将源码文字当作真实页面分析截图。

## 下一页采集

- 下一页 `href` 原值：未取得，首页为验证页。
- 实际 `urljoin()` 下一页结果：未取得。
- 前两页试采：第1页访问验证即停止，未进入第2页。
- 末页按钮：未取得，不能确认完整采集。
- 实际停止原因：访问验证，属于异常中止。

`next_page()` 读取按钮的 `href`；`checked_url()` 用 `urljoin(current_url, href)` 补全链接，并在请求前限定协议、教学站域名、端口及 `/anjuke/` 目录。程序检查重复URL、重复页面指纹和安全页数上限，后续每次请求前明确等待至少1秒，含同站重定向。只有分页区域存在且下一页明确禁用时才能认定末页。

`trial` 只处理前两页，确认页面不同后保存试采清单；`collect` 必须先有同一来源的有效试采清单，并重新核对当前前两页指纹，随后继续采集。分页区域消失、缺按钮、空房源、越站链接、重复URL/页面或达到上限均停止并记错。

上面是已实现的代码规则。实际线上翻页日志、真实 `href` 和末页禁用状态均尚未取得。

**本项截图：未完成。** 本次真实失败日志见前述 `run.json`；没有编造两页翻页日志或末页截图。

## CSV保存与核对

`write_csv_bundle()` 使用 `csv.writer`，按固定8字段写表头，文件参数为 `encoding="utf-8-sig"`、`newline=""`。完整来源页经重新解析后，按8字段完全相同去重，写入同目录临时文件，再用 `csv.DictReader` 回读，核对内容一致后才原子替换标准CSV。

已有CSV必须具有有效来源清单、来源网页和匹配哈希，否则保留并报错。验收清单关联每页原始响应、解码HTML、记录指纹、分页节点、去重前后计数、CSV哈希及首条/第二页首条/末条样本。只有完整来源链与样本检查通过才允许状态为 `ready`。

| CSV验收项 | 实际结果 |
|---|---|
| 真实来源数据 | 未取得 |
| 去重前 / 去重后 | 0 / 0 |
| 完全相同重复数 | 0 |
| CSV数据行数 | 未生成CSV，未做真实数据回读 |
| 首条样本 | 未取得 |
| 跨页样本 | 未取得 |
| 末条样本 | 未取得 |
| 标准CSV路径 / SHA256状态 | `null` / `null` |

**本项截图与真实CSV回读：未完成。** 写入代码具备验收保护，但尚未使用真实房源数据执行，不能写成CSV保存成功。

## 已执行的验证及其范围

在课程容器中执行了语法编译、CLI帮助、Notebook显式参数检查及 `check_safety.py`。保护检查使用本次实际保存的验证页，不构造房源HTML；仅对文件保护使用不含房源含义的临时标记文字，未创建标准CSV。

24项保护检查通过、0项失败，具体记录见 `evidence/safety_checks.json`。包括固定字段顺序、正常相对URL补全、10类越站/异常链接拒绝、真实响应哈希与解码一致、真实验证页立即阻断、Notebook `main([])`、不明来源文件保留、状态协议和未生成标准CSV。

这些检查证明当前边界处理与失败诊断有效。真实房源解析、两页差异、最终末页、真实CSV编码回读及三条业务样本仍待有效来源提供后执行。

## 思考题

1. **怎样取得下一页？** 从下一页按钮读取 `href`，以当前页地址用 `urljoin()` 补全，校验仍属于教学站且未访问过，再等待至少1秒请求。只有明确禁用的末页按钮可以表示完成，其余异常均中止。
2. **结果列表放在哪里？** 放在本次采集函数的局部变量和对应的独立运行目录中。重新执行不会沿用全局列表，避免旧结果混入本轮来源；每次运行证据独立保存。
3. **怎样获取年代？** 在属性项中按年份语义识别，缺失返回空字符串。房源必要字段结构变化时停止并记录，避免通过固定下标取错朝向、楼层等字段。

## 未完成项与继续条件

本阶段尚未完成：Chrome F12选择器复制、真实房源8字段逐项对照、在线两页试采、完整末页确认、真实CSV保存及首条/跨页/末条核验、对应真实截图。完整实验中的数据库与发布工作不由本阶段执行。

继续条件是教学站恢复可访问的真实房源列表，或教师确认提供真实HTML快照及来源。当前不重复索要不存在的快照。有效来源具备后，按 `README.md` 的先试采、再完整采集、最后验收顺序执行。

本次代码和报告由AI协助整理；实际HTTP响应、程序失败日志及保护检查来自课程容器运行。尚未完成的业务结果均保持未完成，没有将预期输出填作真实数据。

## 后续补充：用户浏览器真实DOM快照入口

用户随后提供了真实房源页面的标题节点、Copy selector操作和下一页节点截图。程序现增加显式 `--browser-manifest` 参数，以便读取正常浏览器实际加载后保存的DOM；本节记录程序扩展及安全测试，不把尚待执行的回放/CSV写成已经完成。上文15:34的requests失败属于保留的历史运行记录。

用户复制的原始标题选择器为：

```css
#__layout > div > section > section.list-main > section.list-left > section:nth-child(4) > div:nth-child(1) > a > div.property-content > div.property-content-detail > div.property-content-title > h3
```

从用户截图可见标题具有 `property-content-title-name` 类；在每条 `div.property` 内使用 `h3.property-content-title-name` 即可缩小查找范围。截图还展示了活动下一页节点 `a.next.next-active`，`href="?page=2"`；以当前教学站首页补全得到 `http://www.bspider.top/anjuke/?page=2`。这些来自用户提供的截图和复制文字；完整页数、末页和全部8字段仍需实际来源链核验。

浏览器快照模式的清单须明确 `source="browser_saved"`、`capture_method="browser_dom_serialization"`、实际提供者与捕获时间。每页须有教学站URL、文件名、SHA256、该页捕获时间和实际 `property_count`。程序检查路径范围、文件哈希、容器数及来源模式，拒绝把浏览器快照冒称教师快照或HTTP 200响应。

在 `lab02` 中，真实清单准备好后使用（下面路径对应主代理的实际保存目录）：

```bash
python part2_collection/collect_houses.py trial --browser-manifest part3_storage/browser_capture/20261027T163224/manifest.json
python part2_collection/collect_houses.py collect --browser-manifest part3_storage/browser_capture/20261027T163224/manifest.json --take-pages 8
python part2_collection/collect_houses.py verify
```

此模式的 `source_mode` 为 `browser_snapshot`，HTTP状态码保持 `None`，元数据记录 `content_representation="browser_dom_utf8"`、捕获方法和时间。保存的来源字节使用 `*_browser_dom.html` 与 `snapshot_path/snapshot_sha256`，不叫HTTP原始响应。它属于浏览器DOM快照回放；真实浏览器翻页是否完成应由浏览器操作日志及截图独立证明，不能用文件回放日志替代。

新增 `test_browser_source.py` 已在现有课程容器中执行，11项测试全部通过。测试禁止网络请求，只用不含房源记录的完整性标记检查入口、快照来源标识、时间/容器数、文件变化、路径越界、HTTP状态冒称、参数互斥、混合来源链和协议升级边界；不调用采集写入，不生成标准CSV，不改状态文件。原有online和teacher_snapshot模式保持原接口。

浏览器清单的每页还可记录 `requested_url` 与实际落地 `url`。程序仅接受两者完全一致，或同一主机、路径、查询参数从HTTP升级到HTTPS；文件按请求地址索引，页面元数据保留实际地址。不能借此声明任意跨页、跨路径、跨站跳转或HTTPS降级。
