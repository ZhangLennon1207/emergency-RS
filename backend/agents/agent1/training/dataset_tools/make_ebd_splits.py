# -*- coding: utf-8 -*-
"""
03_make_splits.py

作用：
1. 读取 data/processed/metadata.csv
2. 按 disaster_type 分层随机划分 train / val / test
3. 生成：
   data/processed/splits/train.csv
   data/processed/splits/val.csv
   data/processed/splits/test.csv
   data/processed/splits/split_summary.txt

说明：
- 不移动图片
- 不复制图片
- 只生成训练、验证、测试清单
"""

from pathlib import Path
import csv
import random
from collections import defaultdict

from backend.agents.agent1.training.config import workspace_root


# ============================================================
# 1. 路径设置
# ============================================================

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = workspace_root()

DATA_DIR = PROJECT_ROOT / "data" / "processed"
METADATA_CSV = DATA_DIR / "metadata.csv"

SPLIT_DIR = DATA_DIR / "splits"
SPLIT_DIR.mkdir(parents=True, exist_ok=True)

TRAIN_CSV = SPLIT_DIR / "train.csv"
VAL_CSV = SPLIT_DIR / "val.csv"
TEST_CSV = SPLIT_DIR / "test.csv"
SUMMARY_TXT = SPLIT_DIR / "split_summary.txt"


# ============================================================
# 2. 划分比例与随机种子
# ============================================================

TRAIN_RATIO = 0.70
VAL_RATIO = 0.15
TEST_RATIO = 0.15

RANDOM_SEED = 2026
random.seed(RANDOM_SEED)


# ============================================================
# 3. 读取 metadata.csv
# ============================================================

if not METADATA_CSV.exists():
    raise FileNotFoundError(f"没有找到 metadata.csv：{METADATA_CSV}")

records = []

with open(METADATA_CSV, "r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames

    if fieldnames is None:
        raise ValueError("metadata.csv 为空，无法读取表头。")

    for row in reader:
        records.append(row)

print("=" * 60)
print("开始划分 train / val / test")
print(f"metadata 样本总数：{len(records)}")
print("=" * 60)


# ============================================================
# 4. 基础检查
# ============================================================

required_cols = [
    "sample_id",
    "disaster_type",
    "pre_image",
    "post_image",
    "pre_building_mask",
    "post_damage_mask",
]

for col in required_cols:
    if col not in fieldnames:
        raise ValueError(f"metadata.csv 缺少必要字段：{col}")

sample_ids = [r["sample_id"] for r in records]

if len(sample_ids) != len(set(sample_ids)):
    raise ValueError("metadata.csv 中存在重复 sample_id，请先检查。")


# ============================================================
# 5. 按 disaster_type 分组
# ============================================================

groups = defaultdict(list)

for row in records:
    disaster_type = row["disaster_type"]
    groups[disaster_type].append(row)


# ============================================================
# 6. 对每个灾害类型分别划分
# ============================================================

train_records = []
val_records = []
test_records = []

summary_lines = []
summary_lines.append("训练集 / 验证集 / 测试集划分报告")
summary_lines.append("=" * 60)
summary_lines.append(f"总样本数：{len(records)}")
summary_lines.append(f"随机种子：{RANDOM_SEED}")
summary_lines.append(f"划分比例：train={TRAIN_RATIO}, val={VAL_RATIO}, test={TEST_RATIO}")
summary_lines.append("")
summary_lines.append("各灾害类型划分情况：")
summary_lines.append("-" * 60)

for disaster_type in sorted(groups.keys()):
    items = groups[disaster_type]
    random.shuffle(items)

    n = len(items)

    n_train = int(n * TRAIN_RATIO)
    n_val = int(n * VAL_RATIO)
    n_test = n - n_train - n_val

    train_part = items[:n_train]
    val_part = items[n_train:n_train + n_val]
    test_part = items[n_train + n_val:]

    train_records.extend(train_part)
    val_records.extend(val_part)
    test_records.extend(test_part)

    summary_lines.append(
        f"{disaster_type}: total={n}, train={len(train_part)}, val={len(val_part)}, test={len(test_part)}"
    )


# ============================================================
# 7. 再次打乱整体顺序
# ============================================================

random.shuffle(train_records)
random.shuffle(val_records)
random.shuffle(test_records)


# ============================================================
# 8. 写出 csv
# ============================================================

def write_csv(path, rows, fieldnames):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


write_csv(TRAIN_CSV, train_records, fieldnames)
write_csv(VAL_CSV, val_records, fieldnames)
write_csv(TEST_CSV, test_records, fieldnames)


# ============================================================
# 9. 写出统计报告
# ============================================================

summary_lines.append("")
summary_lines.append("-" * 60)
summary_lines.append(f"train 总数：{len(train_records)}")
summary_lines.append(f"val 总数：{len(val_records)}")
summary_lines.append(f"test 总数：{len(test_records)}")
summary_lines.append(f"合计：{len(train_records) + len(val_records) + len(test_records)}")
summary_lines.append("")
summary_lines.append("输出文件：")
summary_lines.append(str(TRAIN_CSV))
summary_lines.append(str(VAL_CSV))
summary_lines.append(str(TEST_CSV))
summary_lines.append("=" * 60)

with open(SUMMARY_TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(summary_lines))


# ============================================================
# 10. 控制台输出
# ============================================================

print(f"train 样本数：{len(train_records)}")
print(f"val 样本数：{len(val_records)}")
print(f"test 样本数：{len(test_records)}")
print(f"合计样本数：{len(train_records) + len(val_records) + len(test_records)}")
print("=" * 60)
print(f"train.csv：{TRAIN_CSV}")
print(f"val.csv：{VAL_CSV}")
print(f"test.csv：{TEST_CSV}")
print(f"划分报告：{SUMMARY_TXT}")
print("=" * 60)
print("划分完成。")
