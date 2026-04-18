import tempfile
import unittest
from pathlib import Path

from ghost_bot import GhostSolver


class GhostSolverTests(unittest.TestCase):
    def test_prefix_validation_uses_playable_words(self) -> None:
        solver = GhostSolver(["Tree\n", "tread", "DOGMA", "bar", "can't"])

        self.assertTrue(solver.is_prefix(""))
        self.assertTrue(solver.is_prefix("tr"))
        self.assertTrue(solver.is_prefix("tre"))
        self.assertTrue(solver.is_prefix("dog"))
        self.assertFalse(solver.is_prefix("cat"))

        self.assertIn("bar", solver.all_words)
        self.assertNotIn("bar", solver.playable_words)
        self.assertNotIn("can't", solver.all_words)

    def test_completed_word_detection_has_four_letter_minimum(self) -> None:
        solver = GhostSolver(["a", "an", "dog", "bar", "bark", "dogma"])

        self.assertFalse(solver.is_completed_word("a"))
        self.assertFalse(solver.is_completed_word("an"))
        self.assertFalse(solver.is_completed_word("dog"))
        self.assertFalse(solver.is_completed_word("bar"))
        self.assertTrue(solver.is_completed_word("bark"))
        self.assertTrue(solver.is_completed_word("dogma"))

    def test_minimax_winning_and_losing_states(self) -> None:
        solver = GhostSolver(["abcd"])

        self.assertTrue(solver.outcome("").is_winning)
        self.assertFalse(solver.outcome("a").is_winning)
        self.assertTrue(solver.outcome("ab").is_winning)
        self.assertFalse(solver.outcome("abc").is_winning)

        self.assertEqual(solver.recommend("").letter, "a")
        self.assertEqual(solver.recommend("ab").letter, "c")
        self.assertEqual(solver.recommend("abc").action, "no_safe_move")

    def test_tre_e_forms_tree_and_loses_immediately(self) -> None:
        solver = GhostSolver(["tree", "tread"])

        move = solver.evaluate_move("tre", "e")
        self.assertTrue(move.completes_word)
        self.assertFalse(move.is_safe)
        self.assertTrue(move.is_immediate_loss)
        self.assertIn('forms "tree"', move.reason)

    def test_dres_s_forms_dress_with_no_safe_continuation(self) -> None:
        solver = GhostSolver(["dress"])

        move = solver.evaluate_move("dres", "s")
        recommendation = solver.recommend("dres")

        self.assertTrue(move.completes_word)
        self.assertFalse(move.is_safe)
        self.assertEqual(recommendation.action, "no_safe_move")
        self.assertIn('forms "dress"', recommendation.reason)
        self.assertIn("no other continuation is valid", recommendation.reason)

    def test_invalid_move_is_immediate_loss(self) -> None:
        solver = GhostSolver(["ghost", "ghoul"])

        move = solver.evaluate_move("gh", "x")

        self.assertFalse(move.is_valid_prefix)
        self.assertFalse(move.is_safe)
        self.assertTrue(move.is_immediate_loss)

    def test_recommends_challenge_or_call_for_terminal_fragments(self) -> None:
        solver = GhostSolver(["ghost", "ghoul"])

        self.assertEqual(solver.recommend("gx").action, "challenge")
        self.assertEqual(solver.recommend("ghost").action, "call_loss")

    def test_forced_loss_recommendation_delays_as_long_as_possible(self) -> None:
        solver = GhostSolver(["abxy", "acdefg"])

        recommendation = solver.recommend("a")

        self.assertEqual(recommendation.action, "play")
        self.assertEqual(recommendation.letter, "c")
        self.assertEqual(recommendation.status, "losing position")
        self.assertIn("delays the forced loss", recommendation.reason)

    def test_loads_from_dictionary_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "words.txt"
            path.write_text("Tree\nan\nDRESS\nnot-valid\n", encoding="utf-8")

            solver = GhostSolver.from_file(path)

        self.assertTrue(solver.is_completed_word("tree"))
        self.assertTrue(solver.is_completed_word("dress"))
        self.assertFalse(solver.is_completed_word("an"))


if __name__ == "__main__":
    unittest.main()
