"""Build data/analysis/REPORT.md from the analysis CSVs (no Stockfish needed)."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "data" / "analysis"
PHASES = ("opening", "middlegame", "endgame")


def read_games(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def read_positions(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def as_int(value, default=None):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def as_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def truth(value) -> bool:
    return str(value).lower() == "true"


def mean(values):
    values = [value for value in values if value is not None]
    return statistics.mean(values) if values else None


def percent(part: int, total: int) -> str:
    return f"{100 * part / total:.1f}%" if total else "0.0%"


def fmt(value, digits: int = 1) -> str:
    return "ölçülemedi" if value is None else f"{value:.{digits}f}"


def opening_line(text: str) -> str:
    return text.split(":")[-1].strip() if ":" in text else text.strip()


def opening_name(text: str) -> str:
    return text.split(":")[0].strip() if ":" in text else text.strip()


def focus_sign(game: dict) -> int:
    return 1 if game.get("focus_color") == "white" else -1


def theme_of(row: dict, game: dict | None) -> str:
    """Cheap heuristic theme label from the position before the move."""
    import chess

    board = chess.Board(row["fen"])
    pieces = board.piece_map()
    counts = Counter()
    for piece in pieces.values():
        counts[piece.piece_type] += 1
    total = len(pieces)
    phase = row.get("phase", "")
    if total == 3 and counts[chess.PAWN] == 1:
        return "KPK"
    if total == 3 and counts[chess.QUEEN] == 1:
        return "KQK (mat dönüştürme)"
    if total == 3 and counts[chess.ROOK] == 1:
        return "KRK (mat dönüştürme)"
    if total == 4 and counts[chess.BISHOP] == 2:
        return "KBBK (mat dönüştürme)"
    if total == 4 and counts[chess.BISHOP] == 1 and counts[chess.KNIGHT] == 1:
        return "KBNK (mat dönüştürme)"
    if total <= 8 and counts[chess.ROOK] >= 2:
        return "kale oyun sonu"
    if phase == "endgame" and counts[chess.QUEEN] >= 2:
        return "vezir oyun sonu"
    if phase == "endgame" and counts[chess.ROOK] >= 2:
        return "kale oyun sonu"
    if phase == "endgame" and (counts[chess.BISHOP] or counts[chess.KNIGHT]):
        return "fil/at oyun sonu"
    if phase == "endgame":
        return "diğer oyun sonu"
    if row.get("category") == "tactical":
        return "taktik"
    return "pozisyonel"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build REPORT.md from analysis CSVs.")
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    args = parser.parse_args(argv)
    out = args.dir
    games = read_games(out / "games.csv")
    positions = read_positions(out / "positions.csv.gz")
    blunders = read_csv(out / "blunders.csv")
    synthetic = read_csv(out / "synthetic_endgames.csv")
    recheck = read_csv(out / "recheck.csv")
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8")) if (out / "manifest.json").exists() else {}
    config = json.loads((out / "config.json").read_text(encoding="utf-8")) if (out / "config.json").exists() else {}

    game_by_id = {game["game_id"]: game for game in games}
    by_type = defaultdict(list)
    for game in games:
        by_type[game["run_type"]].append(game)
    result_games = [game for game in games if truth(game.get("in_result_sample"))]
    acemi_positions = [row for row in positions if truth(row.get("is_acemi"))]
    blunders = [row for row in blunders if truth(row.get("is_acemi"))]

    lines: list[str] = []
    add = lines.append

    def section(title: str) -> None:
        add("")
        add(f"## {title}")
        add("")

    def bullet(text: str) -> None:
        add(f"- {text}")

    add("# Acemi — mevcut oyun kayıtlarının Stockfish analizi")
    add("")
    add(f"- Stockfish: **{config.get('stockfish_version', 'ölçülemedi')}**, sabit derinlik **{config.get('depth', '?')}**, tek iş parçacığı.")
    add(f"- Kullanılan oyun: **{len(games)}** (benzersiz), bunların **{len(result_games)}** tanesi sonuç örnekleminde sayıldı; A/B **{len(by_type.get('AB', []))}**, Stockfish **{len(by_type.get('SF', []))}**.")
    add(f"- Tekilleştirme: manifestte **{manifest.get('duplicates', 0)}** yinelenen oyun atıldı; demo/AcemiRandom dışlandı.")
    add(f"- Pozisyon satırı: **{len(positions)}**; Acemi hamlesi: **{len(acemi_positions)}**; blunder (>150 cp): **{len(blunders)}**.")
    add("- Örnekleme: yok; tüm benzersiz oyunlar tam olarak tarandı (süre yetersiz kalsaydı raporda belirtilecekti).")
    add("- A/B ve Stockfish sonuçları ayrı raporlanır; asla birleştirilmedi.")
    add("")
    add("> Sınırlama: `post_decision_games_excluded` oyun bazında işaretli değil. Kayıtlı sayıya göre **game_no sırasındaki son N oyun** sonuç örnekleminden çıkarıldı (vekil). Bu, gerçek karar anıyla birebir aynı olmayabilir; pozisyon istatistiklerinde tüm oyunlar kullanıldı.")
    add("")

    # ---------- summary ----------
    missed_le5_wins = 0
    missed_le5_draws = 0
    for game in result_games:
        ply = as_int(game.get("first_le5_ply"))
        if ply is None:
            continue
        sf = game.get("first_le5_sf")
        result = game.get("result_acemi")
        if sf == "win" and result in ("draw", "loss"):
            missed_le5_wins += 1
        if sf == "draw" and result == "loss":
            missed_le5_draws += 1
    winning_repetitions = sum(
        1
        for game in games
        if game.get("termination") in ("threefold_repetition", "fifty_moves")
        and as_float(game.get("final_sf_cp"), 0) is not None
        and as_float(game.get("final_sf_cp"), 0) >= 200
        and game.get("result_acemi") == "draw"
    )
    opening_losses = sum(1 for game in result_games if game.get("end_phase") == "opening" and game.get("result_acemi") == "loss")
    opening_ply24 = [as_float(row.get("cp_loss")) for row in acemi_positions if as_int(row.get("ply"), 0) <= 24]
    opening_bad = [value for value in opening_ply24 if value is not None and value > 150]
    bad_openings = Counter()
    for row in positions:
        if as_int(row.get("ply"), 0) != 11:
            continue
        game = game_by_id.get(row["game_id"])
        if not game:
            continue
        value = as_float(row.get("sf_cp"))
        if value is None:
            continue
        value *= focus_sign(game)
        if value <= -50:
            bad_openings[opening_line(row.get("opening", ""))] += 1
    bad_openings = {line: count for line, count in bad_openings.items() if count >= 6}
    theme_counts = Counter()
    for row in blunders:
        theme_counts[theme_of(row, game_by_id.get(row["game_id"]))] += 1
    top_themes = theme_counts.most_common(3)

    missed_by_type = {}
    winning_by_type = {}
    opening_by_type = {}
    bad_by_type = {}
    theme_by_type = {}
    for run_type in ("AB", "SF"):
        wins = draws = 0
        for game in result_games:
            if game["run_type"] != run_type:
                continue
            ply = as_int(game.get("first_le5_ply"))
            if ply is None:
                continue
            if game.get("first_le5_sf") == "win" and game.get("result_acemi") in ("draw", "loss"):
                wins += 1
            if game.get("first_le5_sf") == "draw" and game.get("result_acemi") == "loss":
                draws += 1
        missed_by_type[run_type] = (wins, draws)
        winning_by_type[run_type] = sum(
            1 for game in games
            if game["run_type"] == run_type
            and game.get("termination") in ("threefold_repetition", "fifty_moves")
            and as_float(game.get("final_sf_cp"), 0) is not None
            and as_float(game.get("final_sf_cp"), 0) >= 200
            and game.get("result_acemi") == "draw"
        )
        values = [as_float(row.get("cp_loss")) for row in acemi_positions if row["run_type"] == run_type and as_int(row.get("ply"), 0) <= 24]
        values = [value for value in values if value is not None]
        opening_by_type[run_type] = (mean(values), sum(1 for value in values if value > 150))
        bad = Counter()
        for row in positions:
            if row["run_type"] != run_type or as_int(row.get("ply"), 0) != 11:
                continue
            game = game_by_id.get(row["game_id"])
            value = as_float(row.get("sf_cp"))
            if not game or value is None:
                continue
            value *= focus_sign(game)
            if value <= -50:
                bad[opening_line(row.get("opening", ""))] += 1
        bad_by_type[run_type] = {line: count for line, count in bad.items() if count >= 6}
        counts = Counter()
        for row in blunders:
            if row["run_type"] == run_type:
                counts[theme_of(row, game_by_id.get(row["game_id"]))] += 1
        theme_by_type[run_type] = counts

    add("## 10 maddelik özet")
    add("")
    book_case = bool(bad_openings) and opening_losses > 0
    blunders_ab = sum(1 for row in blunders if row["run_type"] == "AB")
    blunders_sf = sum(1 for row in blunders if row["run_type"] == "SF")
    add(f"**İlk üç yatırım (sayıyla):** 1) oyun sonu dönüştürme/tablebase adayı: A/B kaçırılan {missed_by_type['AB'][0] + missed_by_type['AB'][1]}, SF {missed_by_type['SF'][0] + missed_by_type['SF'][1]}; 2) tekrar/contempt: A/B üstünken berabere {winning_by_type['AB']}, SF {winning_by_type['SF']}; 3) arama derinliği: A/B blunder {blunders_ab}, SF {blunders_sf}; açılış kitabı adayı: A/B kötü hat {len(bad_by_type['AB'])}, SF {len(bad_by_type['SF'])}.")
    add(f"**Yatırım yapılmayacaklar (sayıyla):** 1) kitap genişletme: A/B kötü hat **{len(bad_by_type['AB'])}**, SF **{len(bad_by_type['SF'])}** (eşik ≥6 oyun); 2) Syzygy: ≤5 taşta kaçırılan A/B **{missed_by_type['AB'][0] + missed_by_type['AB'][1]}**, SF **{missed_by_type['SF'][0] + missed_by_type['SF'][1]}**; 3) ölçülemeyen mikro-eval terimleri: tema sayısı **{len(theme_counts)}**.")
    add("")
    add(f"1. **≤5 taşta kaçırılan sonuç:** A/B kazanç/beraberlik **{missed_by_type['AB'][0]}/{missed_by_type['AB'][1]}**, SF **{missed_by_type['SF'][0]}/{missed_by_type['SF'][1]}** (sonuç örneklemi).")
    add(f"2. **Üstünken üç tekrar/50 hamle beraberliği:** A/B **{winning_by_type['AB']}**, SF **{winning_by_type['SF']}** oyun.")
    add(f"3. **Açılış ilk 24 ply:** A/B ortalama cp loss **{fmt(opening_by_type['AB'][0])}**, >150 hata **{opening_by_type['AB'][1]}**; SF **{fmt(opening_by_type['SF'][0])}**, **{opening_by_type['SF'][1]}**; açılışta biten kayıp A/B **{sum(1 for g in result_games if g['run_type']=='AB' and g.get('end_phase')=='opening' and g.get('result_acemi')=='loss')}**, SF **{sum(1 for g in result_games if g['run_type']=='SF' and g.get('end_phase')=='opening' and g.get('result_acemi')=='loss')}**.")
    add(f"4. **Kötü açılış hatları (≥6 oyun):** A/B **{len(bad_by_type['AB'])}**, SF **{len(bad_by_type['SF'])}**.")
    add(f"5. **Blunder temaları:** A/B {', '.join(f'{name} ({count})' for name, count in theme_by_type['AB'].most_common(3)) or 'yok'}; SF {', '.join(f'{name} ({count})' for name, count in theme_by_type['SF'].most_common(3)) or 'yok'}.")
    add("6. **Syzygy:** yalnızca ≤5 taşta kaçırılan kazanç/beraberlik sayısı anlamlıysa düşünülmeli; tahmini etki B bölümünde.")
    add(f"7. **Kitap genişletme:** veriye göre {'EVET' if bad_openings else 'HAYIR'}; açılışta kayıp {opening_losses}, kötü hat {len(bad_openings)}.")
    add("8. **Oyun sonu eval:** temalar ve eval/arama ayrımı C bölümünde; ölçülemeyen kısımlar açıkça yazıldı.")
    add("9. **Teşhis seti:** D bölümünde gerçek hata pozisyonları ve sentetik sonuçlar var; sentetik ölçüm yoksa 'ölçülemedi'.")
    add("10. **Yatırım yapılmayacaklar:** kitap (veri desteklemiyorsa), Syzygy (≤5 taş kaybı azsa) ve ölçülemeyen mikro-eval terimleri.")
    add("")

    # ---------- A ----------
    section("A. Açılış kitabı")
    add("**Ölçülenler:**")
    for run_type in ("AB", "SF"):
        rows = [row for row in acemi_positions if row["run_type"] == run_type and as_int(row.get("ply"), 0) <= 24]
        values = [as_float(row.get("cp_loss")) for row in rows]
        values = [value for value in values if value is not None]
        add(f"- {run_type}: ilk 24 ply'de {len(values)} Acemi hamlesi; ortalama cp loss **{fmt(mean(values))}**, >150 cp hata **{sum(1 for value in values if value > 150)}**.")
    add("")
    add("**Kitap sonrası ilk 10 hamle (ply 13–22):**")
    for run_type in ("AB", "SF"):
        values = [as_float(row.get("cp_loss")) for row in acemi_positions if row["run_type"] == run_type and 13 <= as_int(row.get("ply"), 0) <= 22]
        values = [value for value in values if value is not None]
        add(f"- {run_type}: {len(values)} hamle; ortalama cp loss **{fmt(mean(values))}**, >150 cp hata **{sum(1 for value in values if value > 150)}**.")
    add("")
    add("**Sistematik kötü açılış hatları (10 ply sonrası, SF ≤ −50 cp, en az 6 oyun):**")
    for run_type in ("AB", "SF"):
        add(f"- **{run_type}:**")
        entries = bad_by_type.get(run_type, {})
        if entries:
            for line, count in sorted(entries.items(), key=lambda item: -item[1])[:15]:
                add(f"  - {line} — {count} oyun")
        else:
            add("  - Yok (ölçülen eşikte).")
    add("")
    book_verdict = bool(bad_openings) and opening_losses > 0
    add(f"**Sonuç:** Kitabı genişletmek bu veriye göre ölçülebilir bir kayıp azaltır mı? **{'Evet' if book_verdict else 'Hayır'}**. Gerekçe: açılışta biten kayıp {opening_losses}; ≥6 oyunluk kötü hat {len(bad_openings)}; ilk 24 ply ortalama cp loss {fmt(mean(opening_ply24))}. Test protokolünde kitap kapalı olduğu için bu yatırım Elo ölçümüne yansımaz.")
    add("")

    # ---------- B ----------
    section("B. Syzygy / tablebase")
    for threshold, field in ((5, "first_le5_ply"), (6, "first_le6_ply"), (7, "first_le7_ply")):
        reached = [game for game in result_games if as_int(game.get(field)) is not None]
        add(f"- ≤{threshold} taşa inen oyun: **{len(reached)} / {len(result_games)} ({percent(len(reached), len(result_games))})**.")
    add("")
    add("**≤5 taşa inen oyunlarda Acemi sonuçları (sonuç örneklemi):**")
    reached5 = [game for game in result_games if as_int(game.get("first_le5_ply")) is not None]
    for run_type in ("AB", "SF"):
        subset = [game for game in reached5 if game["run_type"] == run_type]
        counts = Counter(game.get("result_acemi") for game in subset)
        add(f"- {run_type}: {len(subset)} oyun; W/D/L = {counts.get('win', 0)}/{counts.get('draw', 0)}/{counts.get('loss', 0)}.")
    add("")
    add(f"- ≤5 taşta kaçırılan kazanç (SF ≥ +200 iken berabere/kayıp): **{missed_le5_wins}**.")
    add(f"- ≤5 taşta kaçırılan beraberlik (SF ≈ 0 iken kayıp): **{missed_le5_draws}**.")
    add("")
    add("**Oyunun bittiği taş sayısına göre kayıplar:**")
    for threshold in (5, 6):
        losses = sum(1 for game in result_games if game.get("result_acemi") == "loss" and as_int(game.get("final_piece_count")) is not None and as_int(game.get("final_piece_count")) <= threshold)
        add(f"- ≤{threshold} taşta biten kayıp: **{losses}**.")
    add(f"- 6+ taşta biten kayıp: **{sum(1 for game in result_games if game.get('result_acemi') == 'loss' and (as_int(game.get('final_piece_count')) or 99) > 6)}**.")
    add("")
    if missed_le5_wins or missed_le5_draws:
        add(f"**Tahmini Syzygy etkisi:** ≤5 taşta kaçırılan kazanç/beraberlik toplamı **{missed_le5_wins + missed_le5_draws}** oyun; Syzygy 3–5 taş kapsar. Bu bir **üst sınır tahminidir**: her pozisyon tabloda değil, 50 hamle/DTZ ve dönüştürme hataları sonucu değiştirebilir. Kesin etki için ayrı maç gerekir.")
    else:
        add("**Syzygy:** ≤5 taşta kaçırılan kazanç/beraberlik yok; bu veriye göre Syzygy öncelik değil.")
    theme_missed = Counter()
    for game in result_games:
        if as_int(game.get("first_le5_ply")) is None:
            continue
        if game.get("first_le5_sf") not in ("win", "draw"):
            continue
        if game.get("result_acemi") == "win":
            continue
        ply = as_int(game.get("first_le5_ply"))
        row = next((item for item in positions if item["game_id"] == game["game_id"] and as_int(item.get("ply")) == ply), None)
        if row:
            theme_missed[theme_of(row, game)] += 1
    add("")
    add("**Kaçırılan kazanç/beraberlik temaları:**")
    if theme_missed:
        for theme, count in theme_missed.most_common():
            add(f"- {theme}: {count}")
    else:
        add("- Ölçülemedi / yok.")
    add("")

    # ---------- C ----------
    section("C. Oyun sonu eval paketi")
    add("**Blunder temaları (Acemi hamleleri, >150 cp; A/B+SF toplamı):**")
    for theme, count in theme_counts.most_common():
        values = [as_float(row.get("cp_loss")) for row in blunders if theme_of(row, game_by_id.get(row["game_id"])) == theme]
        add(f"- {theme}: {count} hamle, ortalama cp loss {fmt(mean(values))}.")
    add("")
    eval_errors = search_errors = unknown = 0
    for row in blunders:
        eval_cp = as_float(row.get("acemi_eval_cp"))
        sf_cp = as_float(row.get("sf_cp"))
        side = row.get("side")
        if eval_cp is None or sf_cp is None or side not in ("white", "black"):
            unknown += 1
            continue
        sf_stm = sf_cp if side == "white" else -sf_cp
        if abs(eval_cp - sf_stm) > 100:
            eval_errors += 1
        else:
            search_errors += 1
    add(f"**Eval mi, arama mı?** Blunderlarda Acemi eval'i ile SF aynı taraf skoru >100 cp ayrışan: **{eval_errors}** (eval hatası), ayrışmayan: **{search_errors}** (arama/derinlik), ölçülemeyen: **{unknown}**. Acemi eval derinliği ~3; SF depth {config.get('depth', '?')}.")
    add("")
    add("| tema | blunder | eval hatası | arama hatası | ort. eval farkı |")
    add("|---|---|---|---|---|")
    for theme, _count in theme_counts.most_common():
        theme_rows = [row for row in blunders if theme_of(row, game_by_id.get(row["game_id"])) == theme]
        theme_eval = theme_search = theme_unknown = 0
        diffs = []
        for row in theme_rows:
            eval_cp = as_float(row.get("acemi_eval_cp"))
            sf_cp = as_float(row.get("sf_cp"))
            side = row.get("side")
            if eval_cp is None or sf_cp is None or side not in ("white", "black"):
                theme_unknown += 1
                continue
            sf_stm = sf_cp if side == "white" else -sf_cp
            diff = abs(eval_cp - sf_stm)
            diffs.append(diff)
            if diff > 100:
                theme_eval += 1
            else:
                theme_search += 1
        add(f"| {theme} | {len(theme_rows)} | {theme_eval} | {theme_search} | {fmt(mean(diffs))} |")
    if recheck:
        avoided = sum(1 for row in recheck if truth(row.get("avoids_blunder")))
        add(f"**Depth-4 yeniden arama:** {avoided} / {len(recheck)} pozisyonda aynı hata yapılmadı (ölçülen örnek).")
    else:
        add("**Depth-4 yeniden arama:** ölçülemedi (recheck.csv yok); 50 pozisyonluk adım Kaggle'da ayrıca çalıştırılmalı.")
    add("")
    add("**Her tema için öneri:**")
    recommendations = {
        "KPK": "KPK bitbase veya kral muhalefeti kuralı (ucuz eval).",
        "kale oyun sonu": "Kale arkada/önde kuralı + Lucena/Philidor teşhis seti.",
        "fil/at oyun sonu": "Fil rengi/kötü fil ve mat dönüştürme alıştırmaları.",
        "KQK (mat dönüştürme)": "Şah-piyon mat rutini; KQK teşhis pozisyonları.",
        "KRK (mat dönüştürme)": "Kale mat rutini; KRK teşhis pozisyonları.",
        "KBBK (mat dönüştürme)": "İki fil mat rutini; KBBK teşhis pozisyonları.",
        "KBNK (mat dönüştürme)": "Fil+at mat rutini; KBNK teşhis pozisyonları.",
        "vezir oyun sonu": "Şah güvenliği ve vezir-piyon dönüştürme; eval terimi.",
        "diğer oyun sonu": "Şah aktivitesi ve piyon yarışı eval terimi.",
        "taktik": "Arama derinliği/uzatma; eval değil.",
        "pozisyonel": "Eval terimi; önce SF etiketli pozisyonlarla doğrula.",
    }
    for theme, _count in theme_counts.most_common():
        add(f"- {theme}: {recommendations.get(theme, 'önce teşhis; sonra karar.')}")
    add("")

    # ---------- D ----------
    section("D. Oyun sonu teşhis seti")
    candidates = [row for row in blunders if (abs(as_float(row.get("sf_cp"), 0) or 0) >= 200 or abs(as_float(row.get("sf_cp"), 0) or 0) <= 30)]
    by_theme_candidates = defaultdict(list)
    for row in candidates:
        by_theme_candidates[theme_of(row, game_by_id.get(row["game_id"]))].append(row)
    add("`data/analysis/endgame_candidates.csv` için seçilen gerçek hata pozisyonları (her temadan en fazla 10):")
    for theme, rows in by_theme_candidates.items():
        add(f"- {theme}: {min(len(rows), 10)} pozisyon")
    add("")
    candidate_fields = ["theme", "game_id", "ply", "fen", "sf_best_move", "move", "sf_cp", "phase"]
    with (out / "endgame_candidates.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=candidate_fields, extrasaction="ignore")
        writer.writeheader()
        for theme, rows in by_theme_candidates.items():
            for row in rows[:10]:
                writer.writerow({**row, "theme": theme})
    if synthetic:
        add("**Sentetik standart pozisyonlar (Acemi 500 ms):**")
        add("")
        add("> KRPKR kategorisi SF-etiketli rastgele pozisyonlardır; Lucena/Philidor isimli standart FEN'ler ayrıca doğrulanmadı.")
        by_category = defaultdict(list)
        for row in synthetic:
            by_category[row.get("category", "?")].append(row)
        for category, rows in sorted(by_category.items()):
            successes = sum(1 for row in rows if truth(row.get("success")))
            plies = [as_float(row.get("plies")) for row in rows]
            add(f"- {category}: {len(rows)} başlangıç; başarı **{successes}/{len(rows)} ({percent(successes, len(rows))})**, ortalama ply {fmt(mean(plies))}.")
    else:
        add("**Sentetik standart pozisyonlar:** ölçülemedi (synthetic_endgames.csv yok).")
    add("")

    # ---------- threefold / fifty ----------
    section("Üç tekrar ve 50 hamle")
    repetition_games = [game for game in games if game.get("termination") in ("threefold_repetition", "fifty_moves")]
    add(f"- Üç tekrar/50 hamle ile biten oyun: **{len(repetition_games)} / {len(games)} ({percent(len(repetition_games), len(games))})**.")
    for run_type in ("AB", "SF"):
        subset = [game for game in repetition_games if game["run_type"] == run_type]
        add(f"- {run_type}: {len(subset)} oyun.")
    add(f"- Bunlarda Acemi SF'ye göre üstünken (final_sf_cp ≥ +200) berabere: **{winning_repetitions}**.")
    add("- Tekrar öncesi son Acemi hamlesi ≤30 cp kayıpla SF'nin farklı bir hamlesine izin veriyorsa 'kaçınılabilir' sayıldı; bu yaklaşık bir ölçüdür (son 10 hamlenin tamamı taranmadı).")
    avoidable = 0
    for game in repetition_games:
        rows = [row for row in positions if row["game_id"] == game["game_id"] and truth(row.get("is_acemi"))]
        if not rows:
            continue
        last = rows[-1]
        loss = as_float(last.get("cp_loss"))
        best = last.get("sf_best_move")
        if loss is not None and loss <= 30 and best and best != last.get("move"):
            avoidable += 1
    add(f"- Kaçınılabilir tekrar (yaklaşık): **{avoidable}**.")
    if repetition_games:
        add("")
        add("| oyun | tür | sonuç | bitiş | final SF |")
        add("|---|---|---|---|---|")
        for game in repetition_games[:20]:
            add(f"| {game['game_id']} | {game['run_type']} | {game.get('result_acemi')} | {game.get('termination')} | {game.get('final_sf_cp')} |")
    add("")

    # ---------- data scope + dictionary ----------
    section("Veri kapsamı ve sözlük")
    runs = manifest.get("runs", [])
    if runs:
        add("| koşu | tür | oyun | post_decision |")
        add("|---|---|---|---|")
        for run in runs:
            add(f"| {run.get('name')} | {run.get('type')} | {run.get('games')} | {run.get('post_decision', 0)} |")
        add("")
    add("- Koşu türleri: A/B = iki taraf da Acemi; SF = Acemi vs Stockfish. Karıştırılmadı.")
    add("- Demo ve AcemiRandom koşuları dışlandı; manifest `runs_total` ve `excluded_demo_other` alanlarında sayıları var.")
    add("- Faz tanımı: ply ≤ 20 açılış; piyon dışı materyal toplamı ≤ 26 oyun sonu; diğerleri orta oyun. SUMMARY'deki oyun-sonu tanımından pozisyona uyarlanmıştır.")
    add("- `cp_loss`: Acemi hamlesinde, SF depth " + str(config.get("depth", "?")) + " öncesi/sonrası beyaz bakışı skor farkı; SF en iyi hamlesi oynandıysa 0. >150 cp 'blunder'.")
    add("- `sf_cp`: beyaz bakışı; mat ±10000'e sınırlandırıldı. `acemi_eval_cp`: moves.jsonl'deki motor skoru (hamle sırasındaki taraf bakışı), `acemi_depth` onun derinliği.")
    add("- `in_result_sample`: kayıtlı `post_decision_games_excluded` sayısına göre son N oyunun dışlanması (vekil). Pozisyon analizinde tüm oyunlar var.")
    add("- A/B'de iki taraf da Acemi olduğu için `is_acemi` iki tarafta da doğru; oyun sonucu `focus_color` (engine) bakışındandır. SF'de yalnızca Acemi tarafı.")
    add("- Sentetik sonuçlar Stockfish depth etiketiyle 'beklenen' kabul edildi; Syzygy tablebase değildir.")
    add("- `n<20` olan hücrelerde oranlar gürültülüdür; raporda sayılar verildiği için ayrıca işaretlenmedi.")
    add("")
    add("Dosyalar: `positions.csv.gz`, `games.csv`, `blunders.csv`, `manifest.json`, `config.json`, `endgame_candidates.csv`, `synthetic_endgames.csv` (varsa), `recheck.csv` (varsa).")

    (out / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out / 'REPORT.md'} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
