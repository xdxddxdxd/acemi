"""Ordered columns shared by analysis records, sealed parts and aggregation."""


POSITION_FIELDS = [
    "run_name", "run_type", "game_no", "game_id", "ply", "side", "player", "is_acemi",
    "fen", "move", "acemi_eval_cp", "acemi_depth", "sf_cp", "sf_best_move", "cp_loss",
    "piece_count", "white_pieces", "black_pieces", "phase", "material_balance", "opening",
    "game_result", "tb_wdl", "label_source",
]

GAME_FIELDS = [
    "game_id", "run_name", "run_type", "game_no", "result", "result_acemi", "termination", "opening",
    "focus_color", "plies", "opening_plies", "in_result_sample", "result_sample_proxy", "duplicate_count",
    "acemi_max_sf", "acemi_min_sf", "first_decision_ply", "critical_errors",
    "first_le5_ply", "first_le5_sf", "first_le5_source", "first_le6_ply", "first_le6_sf",
    "first_le6_source", "first_le7_ply", "first_le7_sf", "first_le7_source",
    "final_piece_count", "end_phase", "final_sf_cp",
    "engine_options", "opponent_options", "uci_elo", "move_time_ms", "opening_set",
]

BLUNDER_FIELDS = POSITION_FIELDS + ["category"]
