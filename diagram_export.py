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

from oud2_export import LINE_DEFS, build_full_day_trains, _match_station_indices, _parse_time_to_sec


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


def is_dense_schedule_request(text: str) -> bool:
    """「過密ダイヤ」のような、運転間隔を詰めた高頻度ダイヤを求める発言かどうかを判定する。"""
    return ("過密" in text) or ("高頻度" in text)


def parse_headway_sec(text: str, default: int = 120):
    """「3分間隔」のような指定があれば秒数を返す。なければdefault（デフォルト2分）。"""
    m = re.search(r"(\d{1,3})\s*分\s*(?:間隔|おき|ごと)", text)
    if m:
        minutes = int(m.group(1))
        if 1 <= minutes <= 120:
            return minutes * 60
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
        one_way=line_def.get("one_way", False),
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


def build_diagram_figure(
    line_key: str = "obakyu_main", hour_start: int = 6, hour_end: int = 9, headway_sec: int = None,
):
    """
    縦軸=駅（物理的な並び順）、横軸=時刻のダイヤグラム（Plotlyの図）を作る。
    下りは実線、上りは点線で描き、種別ごとに色分けする。
    headway_secを指定すると、全種別の運転間隔をその秒数に統一する
    （「過密ダイヤ」を見たい場合に使う）。
    """
    line_def = _find_line(line_key)
    stations = line_def["stations"]
    n = len(stations)
    names = [s["name"] for s in stations]

    headways = None
    if headway_sec:
        headways = {name: headway_sec for name in line_def["service_types"]}

    kudari, nobori = build_full_day_trains(
        stations=stations,
        run_times_sec=line_def["run_times_sec"],
        service_types=line_def["service_types"],
        express_times=line_def.get("express_times"),
        one_way=line_def.get("one_way", False),
        headways=headways,
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
    dense_label = f"・運転間隔{headway_sec // 60}分に統一" if headway_sec else ""
    fig.update_layout(
        title=(
            f"{line_def['line_name']} ダイヤグラム "
            f"（{hour_start}:00〜{hour_end}:00、実線=下り・点線=上り{dense_label}）"
        ),
        height=max(500, n * 22),
        margin=dict(l=140, r=20, t=60, b=90),
        plot_bgcolor="white",
    )
    fig.update_xaxes(showgrid=True, gridcolor="#ddd")
    fig.update_yaxes(showgrid=True, gridcolor="#ddd")
    return fig


# ---------------------------------------------------------------------------
# 運転表（スタフ）
# ---------------------------------------------------------------------------
def is_untenhyou_request(text: str) -> bool:
    """「運転表にして」「スタフ作って」のような指示かどうかを判定する。"""
    return ("運転表" in text) or ("スタフ" in text)


def parse_time_unit(text: str, default: str = "sec") -> str:
    """「分単位」「秒単位」の指定があれば読み取る。なければdefault（秒単位）。"""
    if "秒単位" in text:
        return "sec"
    if "分単位" in text:
        return "min"
    return default


def _format_untenhyou_time(value, unit: str) -> str:
    sec = _parse_time_to_sec(value) if isinstance(value, str) else value
    if sec is None:
        return ""
    sec = int(round(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if unit == "min":
        return f"{h}:{m:02d}"
    return f"{h}:{m:02d}:{s:02d}"


def _resolve_train_rows(line_def: dict, train: dict, direction: str, indices: list):
    """
    DIA_JSONの停車駅（通過駅は含まれない）から、経路の始点〜終点まで全駅ぶんの行
    （駅名, 到着時刻文字列またはNone, 発車時刻文字列またはNone, 備考）を組み立てる。
    通過駅は時刻なし・備考「通過」で埋める。
    """
    stations = line_def["stations"]
    name_time = {idx: train["stops"][pos] for pos, idx in enumerate(indices)}
    lo, hi = min(indices), max(indices)
    order = range(lo, hi + 1) if direction == "Kudari" else range(hi, lo - 1, -1)

    rows = []
    for idx in order:
        name = stations[idx]["name"]
        if idx in name_time:
            stop = name_time[idx]
            rows.append((name, stop.get("arrival"), stop.get("departure"), ""))
        else:
            rows.append((name, None, None, "通過"))
    return rows


def _assign_formations(infos: list, min_turnback_sec: int = 180):
    """
    到着駅＝次の列車の発車駅、かつ折り返しに最低min_turnback_sec秒あることを条件に、
    列車どうしを同じ「編成」としてつなげる（貪欲法による簡易的な推定）。
    """
    infos_sorted = sorted(infos, key=lambda x: x["origin_time"] if x["origin_time"] is not None else 0)

    formations = []  # [[info, info, ...], ...]
    available = []   # [(station_idx, avail_time, formation_index), ...]

    for info in infos_sorted:
        best_i, best_avail = None, None
        if info["origin_time"] is not None:
            for i, (st_idx, avail_time, f_idx) in enumerate(available):
                if st_idx != info["origin_idx"] or avail_time is None:
                    continue
                if avail_time + min_turnback_sec <= info["origin_time"]:
                    if best_avail is None or avail_time > best_avail:
                        best_avail, best_i = avail_time, i

        if best_i is not None:
            _, _, f_idx = available[best_i]
            formations[f_idx].append(info)
            available[best_i] = (info["terminus_idx"], info["terminus_time"], f_idx)
        else:
            f_idx = len(formations)
            formations.append([info])
            available.append((info["terminus_idx"], info["terminus_time"], f_idx))

    return formations


def build_untenhyou_html(custom_dia: dict, time_unit: str = "sec", min_turnback_sec: int = 180):
    """
    チャットで実際に作られたダイヤ（DIA_JSON）から、編成（運用）単位でつなげた
    運転表（スタフ）のHTMLを1ファイルで生成する。画面には「列車番号・種別・行き先」の
    ヘッダーと、「駅名・着時刻・発時刻・通過待ち等」の表を列車ごとに並べ、印刷時に
    1列車＝1ページで改ページされるようにしている（番線の列は含めない）。

    戻り値: (HTML文字列をUTF-8エンコードしたbytes, 編成数, 列車数)
    """
    line_key = custom_dia.get("line_key")
    line_def = next((d for d in LINE_DEFS if d["key"] == line_key), None)
    if line_def is None:
        raise ValueError(f"路線キー「{line_key}」が見つかりません。")

    infos = []
    for train in custom_dia.get("trains", []):
        direction = train.get("direction") if train.get("direction") in ("Kudari", "Nobori") else "Kudari"
        stops = train.get("stops") or []
        if not stops:
            continue
        try:
            indices = _match_station_indices(line_def["stations"], train, direction)
        except ValueError:
            continue

        rows = _resolve_train_rows(line_def, train, direction, indices)
        origin_time = _parse_time_to_sec(stops[0].get("departure") or stops[0].get("arrival"))
        terminus_time = _parse_time_to_sec(stops[-1].get("arrival") or stops[-1].get("departure"))

        infos.append(
            {
                "train_number": str(train.get("train_number") or ""),
                "service": train.get("service", ""),
                "destination": rows[-1][0],
                "rows": rows,
                "origin_idx": indices[0],
                "origin_time": origin_time,
                "terminus_idx": indices[-1],
                "terminus_time": terminus_time,
            }
        )

    formations = _assign_formations(infos, min_turnback_sec=min_turnback_sec)

    sheets = []
    for f_idx, trains_in_formation in enumerate(formations, start=1):
        for duty_idx, info in enumerate(trains_in_formation, start=1):
            rows_html = "\n".join(
                f'<tr><td class="station">{name}</td>'
                f'<td class="time">{_format_untenhyou_time(arr, time_unit)}</td>'
                f'<td class="time">{_format_untenhyou_time(dep, time_unit)}</td>'
                f'<td class="note">{note}</td></tr>'
                for name, arr, dep, note in info["rows"]
            )
            sheets.append(f"""<section class="sheet">
  <div class="formation-label">編成{f_idx} - 第{duty_idx}運用</div>
  <table class="headertable">
    <tr><th>列車番号</th><th>種別</th><th>行き先</th></tr>
    <tr><td class="big">{info['train_number']}</td><td class="big">{info['service']}</td><td class="big">{info['destination']}</td></tr>
  </table>
  <table class="maintable">
    <tr><th>駅名</th><th>着時刻</th><th>発時刻</th><th>通過待ち等</th></tr>
    {rows_html}
  </table>
</section>""")

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>運転表</title>
<style>
  body {{ font-family: "Hiragino Sans", "Noto Sans JP", "Yu Gothic", sans-serif; margin: 0; color: #111; }}
  .sheet {{
    page-break-after: always; break-after: page;
    padding: 24px; box-sizing: border-box;
  }}
  .sheet:last-child {{ page-break-after: auto; break-after: auto; }}
  .formation-label {{ font-size: 14px; color: #555; margin-bottom: 6px; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 10px; }}
  th, td {{ border: 1px solid #000; padding: 6px 8px; text-align: center; }}
  th {{ background: #eee; }}
  .headertable .big {{ font-size: 22px; font-weight: bold; padding: 10px; }}
  .maintable td.station {{ text-align: left; font-weight: bold; white-space: nowrap; }}
  .maintable td.time {{ font-variant-numeric: tabular-nums; }}
  @media print {{
    .sheet {{ padding: 12mm; }}
  }}
</style>
</head>
<body>
{''.join(sheets)}
</body>
</html>"""
    return html.encode("utf-8"), len(formations), len(infos)
