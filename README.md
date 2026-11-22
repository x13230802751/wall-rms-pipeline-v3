# 整房间点云 → 识别墙面 → 指定墙面 RMS

输入完整房间点云，不用先给四个点。程序自动提取墙面候选并编号，生成预览页面；你选择墙号后得到该墙区域的 RMS、逐点距离和偏差图。也可以一次计算全部候选，或者再用四点限制局部测区。

**当前可直接运行的是几何识别模式。** 实现参考论文的迭代 RANSAC、DBSCAN 最大连续区域和 SVD 流程，并增加原始测量点恢复。项目没有训练或提供 Point Transformer V3 权重；支持接入外部逐点语义标签，但不把标签接口称为已完成学习模型。柜体、门框、插座和开口内表面可能干扰几何识别，使用前应核对预览。

## 输入与输出

**一句话：给程序一个房间的完整点云，自动生成墙面候选列表；运行 `run --walls all` 可得到每个候选墙的 RMS。**

| 项目 | 具体内容 |
|---|---|
| 必需输入 | 一个房间的完整 XYZ 点云，以及显式指定的坐标单位 `--unit m` 或 `--unit mm`。支持 ASCII/binary PCD、带 x/y/z 表头的 CSV，或 `archive.zip::member.pcd`。不需要预先给四个定位点。 |
| 坐标方向 | 默认 +Z 向上；若点云方向不同，需通过 `--up ux uy uz` 指定向上方向。当前几何发现流程需要识别到可靠地面。 |
| 可选输入 | 几何参数配置 `--config`、外部逐点语义标签 `--labels`；测量时可指定墙号，或另加四点 ROI 限定局部区域。语义标签不是必需输入。 |
| 识别输出 | 自动发现的**墙面候选列表及数量**，每个候选的编号（如 W01）、位置和方向、范围信息、原始点索引及预览。数量由候选列表统计，不预设为四面墙。 |
| 测量输出 | 对全部或指定候选墙分别输出 `rms_mm`（单位 mm），以及选中点数、最佳拟合平面、逐点距离、偏差图和诊断提示。 |

三个命令的输出范围不同：

| 命令 | 输入 | 输出 |
|---|---|---|
| `discover` | 房间点云＋单位 | 候选墙目录 `catalog.json`、候选表 `walls.csv`、点索引 `assignments.npz` 和预览 `index.html` 等；此步骤不生成各墙的正式测量 RMS。 |
| `run --walls all` | 房间点云＋单位 | 上述识别结果，再加全部候选墙的 RMS 汇总 `summary.json`，以及 `measurements/Wxx/` 下各墙的 `result.json`、`distances.csv`、`deviation.png` 和 `histogram.png`。用 `--walls 'W01,W03'` 可只测指定候选。 |
| `measure` | 已生成的 `catalog.json`＋一个墙号；可附加 `--roi` | 该墙或该墙局部区域的一组测量结果，包括 `result.json` 中的 RMS。目录会引用原始点云，因此测量时仍需能读取该点云。 |

这里的墙数量是**算法找到的候选数量**，可能包含误检或漏检，不是已经人工确认的真实墙数。每面墙的 RMS 是该候选实际选中点到其最佳拟合平面的正交距离均方根；存在遮挡或使用局部 ROI 时，结果不代表未观测到的完整墙面。多个独立房间应分别输入、分别运行。

只需要“房间点云＋指定四个定位点 → 该区域 RMS”时，使用另一个仓库 [wall-flatness](https://github.com/x13230802751/wall-flatness-v3)。

## 在这台电脑上开始

在 `E:\博士\选课\7023\wall_rms_pipeline` 打开 PowerShell。项目已配置本地隔离依赖，原始课程数据仍位于相邻 `project/data` 目录。

第一步，自动识别房间墙面：

```powershell
.\run_local.ps1 discover --cloud "../project/data/Point_Cloud_Data.zip::M26.pcd" --unit m --out outputs/my_M26
```

第二步，打开 `outputs/my_M26/index.html`。用下拉框或表格切换墙号，核对俯视位置和墙面投影。页面也生成对应测量命令。W01 等是本次发现的编号，不是官方墙号；换文件、参数或软件版本后必须重新核对。

第三步，测量你选定的一面墙：

```powershell
.\run_local.ps1 measure --catalog outputs/my_M26/catalog.json --wall W03 --out outputs/my_M26_W03
```

看 `result.json` 中的 `rms_mm`，以及 `deviation.png`、`histogram.png`、`distances.csv`。输出目录必须为空或不存在；程序不会覆盖已经保存的实验。

已经完成的本地示例：

- `outputs/M26_v1/index.html` 和 `outputs/M04_v1/index.html`：各四个自动发现的候选墙面。
- `outputs/M26_v1/measurements/` 和 `outputs/M04_v1/measurements/`：各墙测量结果。
- `outputs/M26_W03_selected/`：从目录单独指定 W03 的完整演示。

输出包含课程点云派生内容，仅保留本地，不加入 Git。

## 一次测量全部墙面

```powershell
.\run_local.ps1 run --cloud "../project/data/Point_Cloud_Data.zip::M04.pcd" --unit m --walls all --out outputs/my_M04
```

也可以用 `--walls 'W01,W03'` 指定多个候选。程序保留所有满足几何条件的候选，另外把支持点最多的四面标为 `dominant=true`；不强行把复杂房型改成四面墙。找不到可靠地面或没有有效墙面时明确报错。

## 可选：只测墙面中间一块

`--roi` 是附加限制，不再负责识别房间中是哪面墙。先选墙，再把已选墙点与四点区域求交集。

```powershell
.\run_local.ps1 measure --catalog outputs/my_M26/catalog.json --wall W03 --roi my_roi.json --out outputs/my_local_patch
```

`my_roi.json` 示例格式（坐标是格式示例，不能直接套用官方点云）：

```json
{
  "unit": "m",
  "corners": [[0,0,0],[0,2,0],[0,2,2],[0,0,2]],
  "slab_half_thickness_mm": 50,
  "min_points": 30
}
```

四点为点云坐标系下的三维坐标，按边界顺序排列。ROI 可以声明 m 或 mm，内部转换到 m；其他名称以 `_mm` 结尾的参数始终是毫米。

## 对接队友的语义识别模型

模型输出 N 个整数类别标签，保存为一维 `.npy`，长度和顺序必须与原始输入点云一一对应，包含原始无效点的位置，不得只输出降采样点。默认 0=天花、1=地面、2=墙，其余类别不会进入墙面集合；可在配置 JSON 更改标签编号。

```powershell
.\run_local.ps1 run --cloud room.pcd --unit m --labels predictions.npy --walls all --out outputs/semantic_room
```

模型若使用归一化或降采样点，需要先把预测映射回原始点序。程序校验标签长度和整数类型、记录文件哈希，但无法自动证明标签正确或知道标签来自哪个训练模型。此模式仍由几何算法分开不同墙面。

## 测量定义和参数

每个选中点到最佳拟合平面的垂直距离为 d，`RMS = sqrt(mean(d*d))`，输出单位 mm，按点加权。RMS 是该区域的平面偏差，不自动等同于直尺法、最小区域法或工程合格判定。默认 +Z 向上；若坐标不同，提供 `--up ux uy uz`，不自动猜测重力方向。

| 参数 | 默认 | 作用 |
|---|---:|---|
| `voxel_mm` | 30 | 发现平面的代表点尺度，正式测量回到完整输入 |
| `ransac_mm` | 12 | 发现平面的支持点距离阈值，不是验收限值 |
| `cluster_eps_mm` | 95 | 连通聚类半径，需适合点密度 |
| `floor_touch_mm` | 250 | 候选墙接近地面的容差，考虑遮挡 |
| `recovery_mm` | 50 | 扩展测量集合的法向半厚度；更宽可能混入杂物 |
| `footprint_mm` | 100 | 凸包外支持点附近的横向恢复半径 |

完整默认参数在 `configs/default.json`，通过 `--config configs/default.json` 使用。参数不是针对官方参考 RMS 调优得到的最优值。

每次测量同时输出两种选点方式的结果对照：

- **expanded（默认）**：恢复墙面投影范围和 ±50 mm 厚度内的原始点，保留可能的真实凹凸；凸包会跨过开口，里面的实际杂物点也可能被选中。空洞不造点。
- **paper**：只用发现参考面附近的严格内点，作为论文式几何筛选的对照。它不是论文完整模型复现，可能排除真实鼓包。可用 `--mode paper` 指定。

两者之差是选点敏感性，**不是真值误差**。最终拟合后不再次删除高残差点。`warnings` 需要结合图检查；没有任何输出代表工程验收通过。

## 文件与模块

| 模块 | 输入 | 输出 |
|---|---|---|
| `vendor/io.py` | PCD ASCII/binary、XYZ CSV，支持 ZIP 成员 | XYZ 和输入内容哈希 |
| `planes.py` | 米单位 XYZ、参数 | RANSAC/DBSCAN/SVD 连续平面候选 |
| `discovery.py` | 完整 XYZ，可选语义标签 | 墙面目录、地面、原始点索引、筛选诊断 |
| `measurement.py` | 指定墙点索引、可选 ROI | RMS、拟合面、逐点距离、覆盖诊断 |
| `artifacts.py` / `visuals.py` | 发现和测量结果 | JSON、CSV、NPZ、PNG、本地 HTML |
| `scripts/benchmark.py` | 已知墙身份的合成房间 | 识别质量、测量误差与失败记录 |

发现结果：`catalog.json`、`assignments.npz`、`walls.csv`、`overview.png`、`wall_elevations.png`、`index.html`。测量结果保存输入及目录哈希，重新加载时检查点云和索引文件是否匹配；迁移原始文件可在 `measure` 时用 `--cloud` 指向内容相同的新路径。

## 换电脑安装和复现

Python 3.10+，在本项目根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/benchmark.py --out outputs/new_benchmark
```

当前电脑可使用：

```powershell
.\python_local.ps1 -m unittest discover -s tests -v
.\python_local.ps1 scripts/benchmark.py --out outputs/new_benchmark
.\python_local.ps1 scripts/verify_saved_results.py outputs/M26_v1 outputs/M04_v1 --out outputs/check.json
```

基础安装不需要 PyTorch、训练权重或运行时网络访问。离线网页不依赖 CDN。`scripts/check_viewer.cjs` 是可选浏览器 QA，需 Playwright 和 Edge，不属于测量依赖。

详见 [方法和限制](docs/method.md)、[实验记录](docs/experiments.md)、[复用来源](PROVENANCE.md)。原始课程资料、依赖和点云输出不进入 Git；`results/` 保存可审计数值记录。

## 正式准确性评测

[完整评测方案及实验报告](docs/墙面选择与RMS准确性_评测方案及实验报告.docx)和[评测协议](docs/accuracy_protocol.md)区分墙实例识别、点集选择、RMS 误差、失败率和实体真值。已完成 20 个随机房间 × 15 条件，共 300 场景；两种选点模式及正确语义标签对照产生 720 条评价记录。原始逐例统计与逐墙记录保存在 `results/accuracy_v1/`，不包含课程原始点云。

```powershell
.\python_local.ps1 -m evaluation.runner --out outputs/new_study
.\python_local.ps1 -m evaluation.summarize outputs/new_study
.\python_local.ps1 -m evaluation.audit_records results/accuracy_v1
.\python_local.ps1 -m evaluation.real_stability --archive '../project/data/Point_Cloud_Data.zip' --out outputs/new_stability
.\python_local.ps1 -m evaluation.manual_reference --help
```

正式运行保持生产算法默认参数。部分条件运行可加 `--count 2 --conditions 'clean,bulge60,near_clutter'`；PowerShell 中逗号分隔的参数请使用引号。`manual_reference` 接受独立审定的原始点序实例标签和元数据，模板在 `evaluation/annotation_metadata_template.json`；当前未获得真实房间的盲法审定标签。合成真值、真实数据参数稳定性、固定点集数值一致性均不能替代独立实体精度验证。

Word 报告构建入口为 `evaluation/build_report.py`，额外需要 `python-docx`；它读取固定 `outputs/accuracy_study_v1` 和 `outputs/accuracy_real_stability_v1` 中的已完成记录，不负责重新运行实验。
