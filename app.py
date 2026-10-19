from pathlib import Path
import pandas as pd
import streamlit as st
import altair as alt

st.set_page_config(
    page_title="Broiler Monitoring Dashboard",
    page_icon="🐔",
    layout="wide"
)

st.title("🐔 Broiler Monitoring Dashboard")
st.write("プラットフォーム荷重データの推移を確認するダッシュボードです。")

# データ読み込み
PROJECT_ROOT = Path(__file__).resolve().parent

@st.cache_data
def load_data():
    trial1 = pd.read_csv(
        PROJECT_ROOT / "data/interim/trial1_daily_quality_summary.csv",
        parse_dates=["date"]
    )
    trial2 = pd.read_csv(
        PROJECT_ROOT / "data/interim/trial2_daily_quality_summary.csv",
        parse_dates=["date"]
    )

    trial1["trial"] = "Trial 1"
    trial2["trial"] = "Trial 2"

    return pd.concat([trial1, trial2], ignore_index=True)

daily = load_data()

# Trialを選択
selected_trial = st.selectbox(
    "表示するTrialを選択",
    ["Trial 1", "Trial 2"]
)

trial_data = daily[daily["trial"] == selected_trial]
# 表示するPenを選択
pen_options = sorted(trial_data["pen"].unique())

selected_pens = st.multiselect(
    "表示するPenを選択",
    options=pen_options,
    default=pen_options
)

# グラフ表示用のデータを絞り込む
display_data = trial_data[
    trial_data["pen"].isin(selected_pens)
]

# 表示する日付範囲を選択
min_date = trial_data["date"].min().date()
max_date = trial_data["date"].max().date()

date_range = st.date_input(
    "表示する期間を選択",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

# 日付が2つ選択されている場合のみ絞り込む
if len(date_range) == 2:
    start_date, end_date = date_range

    display_data = display_data[
        (display_data["date"].dt.date >= start_date) &
        (display_data["date"].dt.date <= end_date)
    ]
st.subheader(f"{selected_trial}：Pen別の荷重推移")

# グラフ用にデータを整形
chart_data = display_data.pivot(
    index="date",
    columns="pen",
    values="median_mass"
)

st.line_chart(chart_data)

st.caption(
    "各Penのプラットフォーム荷重の日次中央値を表示しています。"
    "鶏1羽の体重を示すものではありません。"
)
# Pen間差を計算
pen_spread = (
    trial_data.groupby("date")["median_mass"]
    .agg(lambda x: x.max() - x.min())
    .reset_index(name="pen_spread")
    .sort_values("date")
)

# 前日からの変化量
pen_spread["spread_change"] = pen_spread["pen_spread"].diff()

# Pen間差グラフの表示期間だけを絞り込む
if len(date_range) == 2:
    display_pen_spread = pen_spread[
        (pen_spread["date"].dt.date >= start_date) &
        (pen_spread["date"].dt.date <= end_date)
    ]
else:
    display_pen_spread = pen_spread.copy()

st.subheader(f"{selected_trial}：Pen間差の推移")

chart = alt.Chart(display_pen_spread).mark_line().encode(
    x=alt.X("date:T", title="日付"),
    y=alt.Y("pen_spread:Q", title="Pen間差 [kg]"),
    tooltip=["date:T", "pen_spread:Q"]
)

# 急拡大候補の検出基準
chart_threshold = pen_spread["spread_change"].quantile(0.95)

# 急拡大候補の日付を抽出
chart_candidates = display_pen_spread[
    display_pen_spread["spread_change"] >= chart_threshold
].copy()

# 候補日を赤い点で表示
points = alt.Chart(chart_candidates).mark_circle(
    color="red",
    size=120
).encode(
    x="date:T",
    y="pen_spread:Q",
    tooltip=[
        alt.Tooltip("date:T", title="日付"),
        alt.Tooltip("pen_spread:Q", title="Pen間差 [kg]", format=".2f"),
        alt.Tooltip("spread_change:Q", title="前日からの増加量 [kg]", format=".2f")
    ]
)

# 折れ線と赤い点を重ねる
st.altair_chart(chart + points, width="stretch")

st.caption(
    "青い線：Pen間差の日次推移 ／ "
    "赤い点：前日からの増加量が95パーセンタイル以上となった急拡大候補"
)

st.caption(
    "同じ日のPen別中央値の最大値と最小値の差を表示しています。"
)
# 急拡大候補の検出
st.subheader(f"{selected_trial}：Pen間差の急拡大候補")

# Trialごとの95パーセンタイルを基準にする
threshold = pen_spread["spread_change"].quantile(0.95)

# 基準以上の増加があった日を抽出
candidates = pen_spread[
    pen_spread["spread_change"] >= threshold
].copy()

# 選択期間内の急拡大候補だけを表示
display_candidates = candidates[
    (candidates["date"].dt.date >= start_date) &
    (candidates["date"].dt.date <= end_date)
].copy()

# 表示用に列名を変更
display_candidates = display_candidates[
    ["date", "pen_spread", "spread_change"]
].rename(columns={
    "date": "日付",
    "pen_spread": "Pen間差 [kg]",
    "spread_change": "前日からの増加量 [kg]"
})

st.metric("急拡大候補（選択期間内）", f"{len(display_candidates)} 件")

st.write(f"検出基準：前日からの増加量が {threshold:.3f} kg 以上")

st.dataframe(
    display_candidates,
    hide_index=True,
    use_container_width=True
)

st.caption(
    "Trial内の前日変化量の95パーセンタイルを基準とした"
    "探索的な検出結果です。鶏の健康異常を確定するものではありません。"
)

persistence_rate = st.select_slider(
    "継続性の判定基準",
    options=[30, 50, 70, 90],
    value=50,
    format_func=lambda x: f"{x}%"
)
# 急拡大候補の継続性を判定
results = []

for _, candidate in candidates.iterrows():
    candidate_date = candidate["date"]
    candidate_spread = candidate["pen_spread"]

    # 候補日の翌日から3日後まで
    followup = pen_spread[
        (pen_spread["date"] > candidate_date) &
        (pen_spread["date"] <= candidate_date + pd.Timedelta(days=3))
    ]

    # 急拡大日のPen間差の50%を判定基準とする
    persistence_threshold = candidate_spread * (persistence_rate / 100)

    if len(followup) < 3:
        classification = "Insufficient data"
    elif (followup["pen_spread"] >= persistence_threshold).all():
        classification = "Persistent"
    else:
        classification = "Temporary"

    results.append({
        "日付": candidate_date,
        "Pen間差 [kg]": candidate_spread,
        "判定": classification
    })

detection_results = pd.DataFrame(results)

# 継続性判定の表示を選択期間内に限定
display_detection_results = detection_results[
    (detection_results["日付"].dt.date >= start_date) &
    (detection_results["日付"].dt.date <= end_date)
].copy()

st.subheader("急拡大候補の継続性判定")

st.dataframe(
    display_detection_results,
    hide_index=True,
    use_container_width=True
)
st.markdown("### 判定結果の見方")

st.markdown("""
- **Persistent（継続）**：急拡大後の3日間、設定した基準以上のPen間差が続いた状態
- **Temporary（一時的）**：急拡大後の3日間のうち、基準を下回った日がある状態
- **Insufficient data（データ不足）**：判定に必要な3日分のデータがない状態
""")

st.info(
    "この判定は、Pen間差の変化を把握するための探索的な基準です。"
    "鶏の疾病や健康異常を直接診断するものではありません。"
)