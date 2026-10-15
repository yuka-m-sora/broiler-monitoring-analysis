
from pathlib import Path
import pandas as pd

# プロジェクトのルートフォルダ
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 元データと保存先
RAW_DIR = PROJECT_ROOT / "data" / "raw"
OUTPUT_DIR = PROJECT_ROOT / "data" / "interim"


def create_daily_summary(trial_name):
    """Trialごとの日次集計データを作成する"""

    trial_dir = RAW_DIR / trial_name
    files = sorted(trial_dir.glob("*.csv"))

    if not files:
        raise FileNotFoundError(
            f"{trial_dir} にCSVファイルが見つかりません。"
        )

    summary_list = []

    for file in files:
        print(f"処理中: {file.name}")

        temp = pd.read_csv(file)

        # ファイル名から日付を取得
        date = file.stem

        # Penごとの荷重を集計
        stats = (
            temp.groupby("pen")["mass[kg]"]
            .agg(
                count="count",
                min_mass="min",
                median_mass="median",
                max_mass="max"
            )
            .reset_index()
        )

        # 10kgを超える測定値の件数
        over_10 = (
            temp[temp["mass[kg]"] > 10]
            .groupby("pen")
            .size()
            .rename("over_10kg")
            .reset_index()
        )

        stats = stats.merge(over_10, on="pen", how="left")
        stats["over_10kg"] = stats["over_10kg"].fillna(0).astype(int)

        stats.insert(0, "date", date)
        summary_list.append(stats)

    return pd.concat(summary_list, ignore_index=True)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for trial_name in ["trial1", "trial2"]:
        summary = create_daily_summary(trial_name)

        output_path = OUTPUT_DIR / f"{trial_name}_daily_quality_summary.csv"
        summary.to_csv(output_path, index=False)

        print(f"保存完了: {output_path}")
        print(f"データ件数: {len(summary)}")


if __name__ == "__main__":
    main()
