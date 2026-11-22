# 墙面发现与 RMS 评测执行记录

修订与合成实验运行日期：2026-11-22。以下区分本次重新运行的实验和复核使用的官方参考记录。原始课程点云及逐点派生文件不随仓库发布。

## 本次运行

| 项目 | 执行内容 | 结果位置 |
|---|---|---|
| 正式受控评测 | 20 个种子 × 15 个条件，共 300 个场景、720 次方法评估、2960 条目标墙记录 | `results/accuracy_v1/` |
| 功能场景基准 | 14 个场景，13 个完成、1 个稀疏场景失败；52 面匹配墙 | `results/synthetic_records.json`、`synthetic_summary.json` |
| 真实点云稳定性 | M26、M04，各 5 个种子与 2 个厚度设置，共 14 次；参考为默认自动候选，不是人工真值 | `results/accuracy_v1/real_stability.json` |
| 自动测试 | 21 项全部通过 | `results/accuracy_v1/delivery_verification.json` |

正式评测记录全部失败场景，使用 IoU 门槛进行墙实例一对一匹配；漏检、误检、稀疏导致的失败都进入相应分母。正确标签只用作合成 oracle 对照，不代表训练模型的表现。

## 主要结果与解释

干净条件下墙面发现和 RMS 数值计算良好。正确点集上，SVD 与独立协方差特征向量方法的最大 RMS 差约为 1.839e-13 mm；这反映浮点计算一致性，不是扫描仪精度。

25 mm 鼓包条件下，expanded 模式保留缺陷，而 paper 严格内点模式漏掉缺陷。60 mm 鼓包超过默认 50 mm 法向恢复半厚度，两种模式都漏掉缺陷。贴墙杂物会污染 expanded 点集；受影响墙平均绝对误差约 8.072 mm。接地柜板可能产生额外候选；密度梯度和稀疏输入可能造成漏检或无法可靠找到地面。

因此不能用 RMS 更小来判断方法更准确。逐条件墙实例 Precision／Recall／F1、点 IoU、缺陷召回、条件 MAE／RMSE、含失败的成功率、房间 bootstrap 区间及配对差值都保存在正式结果目录中。

## 官方数据及参考边界

M26.pcd 为 793393 点，M04.pcd 为 510190 点，单位 m，+Z 向上。本次真实稳定性实验重新读取原始文件并重新发现候选，没有预设四个角点。默认各发现四个候选。M04 W02 默认 RMS 约 12.689 mm，恢复半厚度改为 20／100 mm 时约为 2.899／23.530 mm。这是对点集选择的敏感性，不应按官方值反向挑参数。

`results/official_measurements.json`、CSV 和 `official_verification.json` 保存经过独立数值及源文件哈希复核的候选测量基线；它们作为参考记录沿用，不表示本次重新采集物理墙面。官方 1.0／1.8 mm 尚未确认对应相同测区和测量定义，不绑定自动墙号，不据此宣称实体精度。

## 复现命令

在仓库根目录安装依赖后执行，输出目录须为空或不存在：

```powershell
python -m evaluation.runner --out outputs/new_study
python -m evaluation.summarize outputs/new_study
python -m evaluation.audit_records outputs/new_study
python scripts/benchmark.py --out outputs/new_functional_study
python -m evaluation.real_stability --archive path/to/Point_Cloud_Data.zip --out outputs/new_stability
python -m unittest discover -s tests -v
```

生产参数未依据成绩调优。每个正式实验保存被测源码哈希、种子、输入及真值哈希、配置、逐墙结果、失败状态和聚合统计。新仓库从当前文件建立一个初始提交；不携带历史快照。独立人工墙面标签和同测区实体参考测量仍需补充。
