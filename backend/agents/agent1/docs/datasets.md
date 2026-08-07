# Agent1 数据集说明

数据集不进入 GitHub。训练人员应自行从官方或已获授权的来源准备数据，并遵守原始许可证。

| 数据集 | 用途 | 仓库记录内容 |
| --- | --- | --- |
| EBD/xBD 派生数据 | 建筑分割、建筑损伤分类、流水线回归 | 数据准备脚本、划分算法和随机种子 |
| OpenEarthMap | 道路二值分割 | 道路类别映射和划分脚本 |
| SpaceNet8 | 道路状态分类 | 几何检查、栅格化和划分脚本 |

外部工作区应包含 `data/`、`agent1_visual_evidence/checkpoints/` 和运行输出目录。通过 `AGENT1_WORKSPACE` 指向该工作区；仓库源码中不得写个人绝对路径。

EBD 划分由 `training/dataset_tools/make_ebd_splits.py` 按脚本固定随机种子重建；不提交原始划分 CSV 或任何遥感影像。数据数量、版本、来源链接和许可证应在实际交付时由数据负责人补充核验。
