# -*- coding: utf-8 -*-
"""
運転計画（乗務員行路表の簡易版）とダイヤグラム（時刻-距離線図）を生成するモジュール。

- 運転計画: 1本の列車について、停車駅ごとの着時刻・発(通過)時刻を並べたシンプルな
  HTML表。ユーザーから提供されたサンプル画像をもとに、運転時分・車両最高速度・
  速度種別・けん引定数・制限速度・番線・記事・帳票ヘッダー（達第○号や運輸区名など）
  は省いた最小構成にしている。
- ダイヤグラム: 縦軸に駅（物理的な並び順）、横軸に時刻を取り、列車ごとに停車点を
  結んだ線を引く、いわゆる「ダイヤグラム」。Plotlyで生成し、ブラウザ側のフォントで
  描画されるようにすることで、日本語（駅名）が文字化けしない構成にしている
  （サーバー側でフォントを用意する必要がある画像生成ライブラリは使っていない）。
"""

import re

import plotly.graph_objects as go

from oud2_export import LINE_DEFS, build_full_day_trains


def _find_line(line_key: str) -> dict:
    return next(d for d in LINE_DEFS if d["key"] == line_key)


def parse_line_key(text: str, default: str = "obakyu_main") -> str:
    """メッセージ中に路線名が含まれていれば、その路線のキーを返す。"""
    for line_def in LINE_DEFS:
        if line_def["line_name"] in text:
            return line_def["key"]
    return default


def parse_hour_range(text: str, default=(6, 9)):
    """「7時から10時」のような指定があれば (開始時, 終了時) を返す。なければdefault。"""
    m = re.search(r"(\d{1,2})\s*時\s*(?:から|〜|-|~)\s*(\d{1,2})\s*時", text)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if 0 <= a < 24 and 0 < b <= 24 and a < b:
            return a, b
    return default


def parse_train_number(text: str):
    """メッセージ中に列車番号らしき数字列があれば返す。"""
    m = re.search(r"(\d{4,6})", text)
    return m.group(1) if m else None


def _sec_to_hhmm(total_seconds) -> str:
    total_seconds = int(round(total_seconds))
    h, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    if s == 0:
        return f"{h}:{m:02d}"
    return f"{h}:{m:02d}:{s:02d}"


# ---------------------------------------------------------------------------
# 運転計画（行路表の簡易版）
# ---------------------------------------------------------------------------
def build_untenkeikaku_html(line_key: str = "obakyu_main", train_number: str = None, direction: str = "Kudari"):
    """
    指定した列車1本ぶんの、停車駅・着時刻・発(通過)時刻だけのシンプルな運転計画表を
    HTMLで生成する。train_numberを指定しない場合は、その路線・方向の最初の列車を使う。
    戻り値: (HTML文字列をUTF-8エンコードしたbytes, 実際に使われた列車番号, 実際の方向)
    """
    line_def = _find_line(line_key)
    stations = line_def["stations"]
    kudari, nobori = build_full_day_trains(
        stations=stations,
        run_times_sec=line_def["run_times_sec"],
        service_types=line_def["service_types"],
        express_times=line_def.get("express_times"),
    )

    train = None
    used_direction = direction
    if train_number:
        for cand_direction, trains in (("Kudari", kudari), ("Nobori", nobori)):
            found = next((t for t in trains if t["train_number"] == str(train_number)), None)
            if found:
                train = found
                used_direction = cand_direction
                break

    if train is None:
        trains = kudari if used_direction == "Kudari" else nobori
        train = trains[0]

    n = len(stations)
    order = range(n) if used_direction == "Kudari" else range(n - 1, -1, -1)

    rows = []
    for idx in order:
        if idx not in train["stops"]:
            continue
        arr, dep = train["stops"][idx]
        if arr is None and dep is None:
            continue  # 通過駅はこの簡易版では省略する
        arr_str = _sec_to_hhmm(arr) if arr is not None else ""
        dep_str = _sec_to_hhmm(dep) if dep is not None else ""
        rows.append((stations[idx]["name"], arr_str, dep_str))

    service_name = line_def["service_types"][train["service_index"]]
    direction_label = "下り" if used_direction == "Kudari" else "上り"

    html_rows = "\n".join(
        f'<tr><td class="station">{name}</td><td class="time">{arr}</td><td class="time">{dep}</td></tr>'
        for name, arr, dep in rows
    )

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>運転計画 {train['train_number']}</title>
<style>
  body {{ font-family: "Hiragino Sans", "Noto Sans JP", "Yu Gothic", sans-serif; margin: 24px; color: #111; }}
  h1 {{ font-size: 20px; margin-bottom: 4px; }}
  .sub {{ color: #555; margin-bottom: 16px; }}
  .trainno {{
    font-size: 40px; font-weight: bold; text-align: center;
    border: 2px solid #000; padding: 10px; width: 260px; margin-bottom: 16px;
  }}
  table {{ border-collapse: collapse; width: 100%; max-width: 480px; }}
  th, td {{ border: 1px solid #000; padding: 6px 14px; }}
  th {{ background: #eee; text-align: center; }}
  td.station {{ text-align: left; font-weight: bold; white-space: nowrap; }}
  td.time {{ text-align: center; font-variant-numeric: tabular-nums; font-size: 18px; }}
</style>
</head>
<body>
  <h1>運転計画</h1>
  <div class="sub">{line_def['line_name']}　{direction_label}　{service_name}</div>
  <div class="trainno">{train['train_number']}</div>
  <table>
    <tr><th>停車駅名</th><th>着</th><th>発(通)</th></tr>
    {html_rows}
  </table>
</body>
</html>"""
    return html.encode("utf-8"), train["train_number"], used_direction


# ---------------------------------------------------------------------------
# ダイヤグラム
# ---------------------------------------------------------------------------
_PALETTE = ["black", "red", "green", "blue", "orange", "purple", "brown", "teal"]


def build_diagram_figure(line_key: str = "obakyu_main", hour_start: int = 6, hour_end: int = 9):
    """
    縦軸=駅（物理的な並び順）、横軸=時刻のダイヤグラム（Plotlyの図）を作る。
    下りは実線、上りは点線で描き、種別ごとに色分けする。
    """
    line_def = _find_line(line_key)
    stations = line_def["stations"]
    n = len(stations)
    names = [s["name"] for s in stations]

    kudari, nobori = build_full_day_trains(
        stations=stations,
        run_times_sec=line_def["run_times_sec"],
        service_types=line_def["service_types"],
        express_times=line_def.get("express_times"),
    )

    color_map = {
        name: _PALETTE[i % len(_PALETTE)] for i, name in enumerate(line_def["service_types"])
    }

    x_min, x_max = hour_start * 3600, hour_end * 3600
    fig = go.Figure()

    def add_trains(trains: list, dash: str):
        for train in trains:
            xs, ys = [], []
            for idx in range(n):
                if idx not in train["stops"]:
                    continue
                arr, dep = train["stops"][idx]
                if arr is None and dep is None:
                    continue
                t = arr if arr is not None else dep
                xs.append(t)
                ys.append(idx)
                if arr is not None and dep is not None and dep != arr:
                    xs.append(dep)
                    ys.append(idx)
            if not xs:
                continue
            if max(xs) < x_min or min(xs) > x_max:
                continue
            service = line_def["service_types"][train["service_index"]]
            fig.add_trace(
                go.Scatter(
                    x=xs, y=ys, mode="lines",
                    line=dict(color=color_map.get(service, "black"), width=1, dash=dash),
                    name=f"{service} {train['train_number']}",
                    hoverinfo="name",
                    showlegend=False,
                )
            )

    add_trains(kudari, "solid")
    add_trains(nobori, "dot")

    tick_vals = list(range(x_min, x_max + 1, 600))
    fig.update_yaxes(
        tickmode="array", tickvals=list(range(n)), ticktext=names,
        autorange="reversed",
    )
    fig.update_xaxes(
        tickmode="array", tickvals=tick_vals,
        ticktext=[_sec_to_hhmm(v) for v in tick_vals],
        tickangle=45, range=[x_min, x_max],
    )
    fig.update_layout(
        title=(
            f"{line_def['line_name']} ダイヤグラム "
            f"（{hour_start}:00〜{hour_end}:00、実線=下り・点線=上り）"
        ),
        height=max(500, n * 22),
        margin=dict(l=140, r=20, t=60, b=90),
        plot_bgcolor="white",
    )
    fig.update_xaxes(showgrid=True, gridcolor="#ddd")
    fig.update_yaxes(showgrid=True, gridcolor="#ddd")
    return fig
