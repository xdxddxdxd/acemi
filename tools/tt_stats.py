"""Diagnostic-only Searcher subclass. Production engine and TT policy stay untouched.

Times include instrumentation overhead and are not speed/strength measurements.
Only interior _probe calls are counted; root's direct move-hint lookup is excluded.
"""

from engine.search import Searcher, TT_EXACT, TT_LOWER, TT_UPPER, from_tt_score

MAX_FIELDS = ('max_occupancy', 'max_stored_history')
PAIR_FIELDS = ('second_slot_accepts', 'second_slot_depth_sufficient', 'second_slot_cutoffs',
               'second_slot_additions', 'context_evictions')
FIELDS = (
    'probes', 'misses', 'hits', 'hints_available', 'null_rejected',
    'context_rejected', 'clock_mismatch', 'history_mismatch', 'same_clock_history_mismatch',
    'other_context_mismatch', 'accepted', 'no_window', 'too_shallow', 'sufficient_depth',
    'cutoff_exact', 'cutoff_lower', 'cutoff_upper', 'bound_no_cutoff',
    'store_attempts', 'store_disabled', 'store_null', 'stores', 'insertions',
    'replacements_same_context', 'replacements_new_context', 'deeper_preserved',
    'capacity_clears', 'capacity_entries_discarded', 'explicit_clears',
    'explicit_entries_discarded', *MAX_FIELDS,
    *PAIR_FIELDS,
)


def empty_stats():
    return dict.fromkeys(FIELDS, 0)


def add_stats(total, part):
    for key in FIELDS:
        total[key] = max(total[key], part.get(key, 0)) if key in MAX_FIELDS else total[key] + part.get(key, 0)


def validate_stats(s):
    s = {**dict.fromkeys(PAIR_FIELDS, 0), **s}  # Historical v1 diagnostics remain readable.
    checks = (
        s['probes'] == s['misses'] + s['hits'],
        s['hits'] == s['null_rejected'] + s['context_rejected'] + s['accepted'],
        s['accepted'] == s['no_window'] + s['too_shallow'] + s['sufficient_depth'],
        s['sufficient_depth'] == s['cutoff_exact'] + s['cutoff_lower'] + s['cutoff_upper'] + s['bound_no_cutoff'],
        s['store_attempts'] == s['store_disabled'] + s['store_null'] + s['deeper_preserved'] + s['stores'],
        s['stores'] == s['insertions'] + s['replacements_same_context'] + s['replacements_new_context'],
        all(type(s[k]) is int and s[k] >= 0 for k in FIELDS),
    )
    if not all(checks):
        raise ValueError('TT diagnostic counters are inconsistent')


class TTDiagnosticSearcher(Searcher):
    def __init__(self, *args, **kwargs):
        self._tt_window = None
        super().__init__(*args, **kwargs)
        self.reset_tt_stats()

    def reset_tt_stats(self):
        """Reset measurement only, retaining the warm TT between game positions."""
        self.tt_stats = empty_stats()
        self.tt_stats['max_occupancy'] = self.tt_size

    def snapshot_tt_stats(self):
        validate_stats(self.tt_stats)
        return self.tt_stats.copy()

    def clear_tt(self):
        if hasattr(self, 'tt_stats'):
            self.tt_stats['explicit_clears'] += 1
            self.tt_stats['explicit_entries_discarded'] += self.tt_size
        super().clear_tt()

    def _negamax(self, board, depth, alpha, beta, ply, allow_null=True, extensions=0):
        if depth <= 0:
            return super()._negamax(board, depth, alpha, beta, ply, allow_null, extensions)
        previous = self._tt_window
        self._tt_window = (depth, alpha, beta, ply)
        try:
            return super()._negamax(board, depth, alpha, beta, ply, allow_null, extensions)
        finally:
            self._tt_window = previous

    def _probe(self, board):
        raw = self._tt.get(board.zobrist_hash)
        entry, hint = super()._probe(board)
        s = self.tt_stats
        s['probes'] += 1
        if raw is None:
            s['misses'] += 1
            return entry, hint
        s['hits'] += 1
        s['hints_available'] += int(hint is not None)
        if entry is None:
            if board.null_stack:
                s['null_rejected'] += 1
            else:
                s['context_rejected'] += 1
                context = self._tt_context(board)
                clock = raw.context[0] != context[0]
                history = raw.context[1] != context[1]
                s['clock_mismatch'] += int(clock)
                s['history_mismatch'] += int(history)
                s['same_clock_history_mismatch'] += int(history and not clock)
                s['other_context_mismatch'] += int(raw.context[2:] != context[2:])
            return entry, hint
        s['accepted'] += 1
        secondary_hit = (self.use_tt_two_contexts and
                         entry is self._tt_secondary.get(board.zobrist_hash))
        s['second_slot_accepts'] += int(secondary_hit)
        if self._tt_window is None:
            s['no_window'] += 1
            return entry, hint
        depth, alpha, beta, ply = self._tt_window
        if entry.depth < depth:
            s['too_shallow'] += 1
        else:
            s['sufficient_depth'] += 1
            s['second_slot_depth_sufficient'] += int(secondary_hit)
            # Mirrors the immediate return in Searcher._negamax, without changing it.
            score = from_tt_score(entry.score, ply)
            if entry.flag == TT_EXACT:
                s['cutoff_exact'] += 1
                s['second_slot_cutoffs'] += int(secondary_hit)
            elif entry.flag == TT_LOWER and score >= beta:
                s['cutoff_lower'] += 1
                s['second_slot_cutoffs'] += int(secondary_hit)
            elif entry.flag == TT_UPPER and score <= alpha:
                s['cutoff_upper'] += 1
                s['second_slot_cutoffs'] += int(secondary_hit)
            else:
                s['bound_no_cutoff'] += 1
        return entry, hint

    def _store(self, board, depth, flag, score, move):
        s = self.tt_stats
        s['store_attempts'] += 1
        if self._tt_max <= 0:
            s['store_disabled'] += 1
        elif board.null_stack:
            s['store_null'] += 1
        else:
            old = self._tt.get(board.zobrist_hash)
            secondary = self._tt_secondary.get(board.zobrist_hash) if self.use_tt_two_contexts else None
            context = self._tt_context(board)
            same = old is not None and old.context == context
            match = old if same else secondary if secondary is not None and secondary.context == context else None
            if match is not None and match.depth > depth:
                s['deeper_preserved'] += 1
            else:
                s['stores'] += 1
                if old is None:
                    s['insertions'] += 1
                else:
                    s['replacements_same_context' if match is not None else 'replacements_new_context'] += 1
                adding = old is None or (self.use_tt_two_contexts and match is None and secondary is None)
                if adding and self.tt_size >= self._tt_max:
                    s['capacity_clears'] += 1
                    s['capacity_entries_discarded'] += self.tt_size
                elif self.use_tt_two_contexts and old is not None and match is None:
                    s['second_slot_additions' if secondary is None else 'context_evictions'] += 1
                s['max_stored_history'] = max(s['max_stored_history'], len(context[1]))
        super()._store(board, depth, flag, score, move)
        s['max_occupancy'] = max(s['max_occupancy'], self.tt_size)
