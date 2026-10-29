"""Which games count towards a result: pairs and the frozen SPRT sample (no engines)."""

import unittest

from tools import pairing


def game(game_no: int, result: str = "win") -> dict:
    return {"game_no": game_no, "pair_no": game_no // 2, "engine_result": result}


class CompletedPairsTests(unittest.TestCase):
    def test_keeps_only_complete_pairs(self) -> None:
        games = [game(0), game(1), game(2)]
        self.assertEqual([g["game_no"] for g in pairing.completed_pairs(games)], [0, 1])

    def test_aborted_partner_breaks_the_pair(self) -> None:
        games = [game(0), game(1, "aborted"), game(2), game(3)]
        self.assertEqual([g["game_no"] for g in pairing.completed_pairs(games)], [2, 3])


class SelectSampleTests(unittest.TestCase):
    def test_without_sprt_every_finished_game_counts(self) -> None:
        games = [game(0), game(1), game(2), game(3, "aborted")]
        sample = pairing.select_sample(games, sprt_enabled=False, decided_games=None)
        self.assertEqual(len(sample.games), 3)
        self.assertEqual((sample.unpaired_excluded, sample.post_decision_excluded), (0, 0))

    def test_sprt_without_decision_uses_pairs_of_all_games(self) -> None:
        games = [game(0), game(1), game(2)]
        sample = pairing.select_sample(games, sprt_enabled=True, decided_games=None)
        self.assertEqual([g["game_no"] for g in sample.games], [0, 1])
        self.assertEqual((sample.unpaired_excluded, sample.post_decision_excluded), (1, 0))

    def test_sample_is_frozen_at_the_decision(self) -> None:
        at_decision = [game(0), game(1), game(2)]
        # Games 3 and 4 finished after the decision (they were in flight).
        everything = at_decision + [game(3, "loss"), game(4, "loss")]
        sample = pairing.select_sample(everything, sprt_enabled=True, decided_games=at_decision)
        self.assertEqual([g["game_no"] for g in sample.games], [0, 1])
        self.assertEqual(sample.unpaired_excluded, 1)  # game 2 had no partner at the decision
        self.assertEqual(sample.post_decision_excluded, 2)

    def test_aborted_games_are_not_counted_as_excluded(self) -> None:
        at_decision = [game(0), game(1)]
        everything = at_decision + [game(2, "aborted")]
        sample = pairing.select_sample(everything, sprt_enabled=True, decided_games=at_decision)
        self.assertEqual(sample.post_decision_excluded, 0)


if __name__ == "__main__":
    unittest.main()
