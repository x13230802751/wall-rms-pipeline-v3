# 复用来源

复用用户原有私有项目 `civl7023-wall-flatness` 的固定提交
`56407caf4d1ec3c2234c890936cbf0677f6cda51` 中：

- `code/wall_flatness/io.py` → `room_walls/vendor/io.py`：点云读取和内容哈希。
- `code/wall_flatness/geometry.py` → `room_walls/vendor/geometry.py`：SVD、四点合法性和选区。

这是源码快照，不依赖相邻旧项目的可变代码。当前来源归属和使用权限沿用用户自己的原项目；没有引入外部未核实授权的算法源码。SHA256 详见 `vendor_provenance.json`，跨系统核对时使用 LF 归一化值。

新编写部分包括自动平面发现、DBSCAN、地面/墙面筛选、原始点恢复、目录索引和验证、命令行、预览页及整房间评测。论文提供方法参考，没有复制其模型代码或训练权重。
