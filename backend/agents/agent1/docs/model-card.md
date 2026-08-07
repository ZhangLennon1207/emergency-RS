# Agent1 模型卡

## 组成与权重身份

权重不存放在本仓库。模型电脑必须使用下表文件，并在首次联调前核对完整 SHA-256。

| 能力 | 模型类 | 权重文件 | 字节数 | SHA-256 |
| --- | --- | --- | ---: | --- |
| 建筑二值分割 | `BuildingUNet` | `building_unet_medium_best.pth` | 23247243 | `221F33B2B52A8D3BDCFEBF5423AAADFCA459EE032A12F8AD734E08A0D8B157B3` |
| 建筑损伤五分类 | `DamageUNet` | `damage_unet_7ch_best.pth` | 23261595 | `1347D4D423F474B3B3BC1A05F5BE8C01724FAB0C7B67055C26E5735560203F8D` |
| 道路二值分割 | `RoadUNet` | `road_unet_best.pth` | 93276407 | `CCA01756D695086BBABA8FF14431DDEB106B5B7FF80BC6FBD2E2E54EBA6BFA45` |
| 道路状态三分类 | `AttentionResUNet7ch` | `road_status_attresunet7ch_best.pth` | 200192633 | `69F79447EE7AFD68C022C3C635DD6252672F12544DF696F5188991D344CB92F3` |

`18_predict_building_damage_same20.py` 是历史兼容推理脚本，不是第五个模型。正式流水线直接导入 `src/models/` 中与训练 checkpoint 对应的模型结构。

## 已有离线证据

- 建筑模型最佳记录：验证 IoU `0.758560`，Dice `0.827288`。
- 损伤模型最终记录：验证前景 mIoU `0.259076`；细分类别仍存在明显不平衡。
- 道路二值模型最佳记录：验证 IoU `0.442389`，Dice `0.613412`。
- 道路状态模型 91 条测试：道路 mIoU `0.660323`；后处理后 `0.665672`。
- Agent1 固定种子随机 20 条批量运行：20 条成功、0 条失败。

这些数字来自旧项目已有日志和汇总文件，仅用于迁移回归，不代表跨数据集泛化结论。
