#!/usr/bin/env python3
"""Optimal Ghost word-game bot.

README / usage examples:

    python ghost_bot.py --dict words.txt
    python ghost_bot.py --dict words.txt --fragment dres
    python ghost_bot.py --dict words.txt --fragment tre --show-invalid
    python ghost_bot.py --dict words.txt --interactive
    python ghost_bot.py --dict words.txt --interactive --bot-first

The dictionary file should contain one word per line. Words are normalized to
lowercase ASCII alphabetic text. Ghost only treats words of length 4 or more as
round-ending completed words; shorter dictionary entries are loaded but are not
playable terminal words.
"""

from __future__ import annotations

import argparse
import string
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional


ALPHABET = string.ascii_lowercase
MIN_WORD_LENGTH = 4


@dataclass
class TrieNode:
    """A node in the trie of playable dictionary words."""

    children: dict[str, "TrieNode"] = field(default_factory=dict)
    is_word: bool = False


@dataclass(frozen=True)
class Outcome:
    """Perfect-play result for the player whose turn it is."""

    is_winning: bool
    plies_to_end: int


@dataclass(frozen=True)
class MoveEvaluation:
    """Evaluation of adding one letter to a fragment."""

    letter: str
    resulting_fragment: str
    is_valid_prefix: bool
    completes_word: bool
    can_be_extended: bool
    is_safe: bool
    is_winning: bool
    plies_to_end: int
    reason: str

    @property
    def is_immediate_loss(self) -> bool:
        """Return True when this move loses before the opponent moves."""

        return not self.is_safe and not self.is_winning


@dataclass(frozen=True)
class Recommendation:
    """The bot's recommended action for the current fragment."""

    action: str
    letter: Optional[str]
    resulting_fragment: str
    status: str
    reason: str
    plies_to_end: int

    @property
    def action_text(self) -> str:
        """Return user-facing text for the recommended action."""

        if self.action == "play" and self.letter is not None:
            return f"play '{self.letter}'"
        if self.action == "challenge":
            return "challenge"
        if self.action == "call_loss":
            return "call the loss"
        return "no safe letter exists"


class GhostSolver:
    """Solve Ghost positions with trie-backed minimax search."""

    def __init__(
        self, words: Iterable[str], min_word_length: int = MIN_WORD_LENGTH
    ) -> None:
        self.min_word_length = min_word_length
        self.root = TrieNode()
        self.all_words: set[str] = set()
        self.playable_words: set[str] = set()

        for word in self.normalize_words(words):
            self.all_words.add(word)
            if len(word) >= min_word_length:
                self.playable_words.add(word)
                self._insert(word)

    @classmethod
    def from_file(
        cls, path: str | Path, min_word_length: int = MIN_WORD_LENGTH
    ) -> "GhostSolver":
        """Build a solver from a newline-delimited dictionary file."""

        dictionary_path = Path(path)
        with dictionary_path.open("r", encoding="utf-8") as handle:
            return cls(handle, min_word_length=min_word_length)

    @staticmethod
    def normalize_word(raw_word: str) -> Optional[str]:
        """Normalize one raw dictionary entry, or return None if unusable."""

        word = raw_word.strip().lower()
        if word and word.isascii() and word.isalpha():
            return word
        return None

    @classmethod
    def normalize_words(cls, words: Iterable[str]) -> Iterable[str]:
        """Yield normalized ASCII alphabetic words from an iterable."""

        for raw_word in words:
            word = cls.normalize_word(raw_word)
            if word is not None:
                yield word

    @staticmethod
    def normalize_fragment(fragment: str) -> str:
        """Normalize and validate a fragment supplied by a user or caller."""

        normalized = fragment.strip().lower()
        if normalized and (not normalized.isascii() or not normalized.isalpha()):
            raise ValueError("fragment must contain only ASCII letters")
        return normalized

    @staticmethod
    def normalize_letter(letter: str) -> str:
        """Normalize and validate a one-letter move."""

        normalized = letter.strip().lower()
        if len(normalized) != 1 or normalized not in ALPHABET:
            raise ValueError("move must be exactly one ASCII letter")
        return normalized

    def _insert(self, word: str) -> None:
        node = self.root
        for letter in word:
            node = node.children.setdefault(letter, TrieNode())
        node.is_word = True

    def _find_node(self, fragment: str) -> Optional[TrieNode]:
        node = self.root
        for letter in fragment:
            child = node.children.get(letter)
            if child is None:
                return None
            node = child
        return node

    def is_prefix(self, fragment: str) -> bool:
        """Return whether the fragment is a prefix of a playable word."""

        fragment = self.normalize_fragment(fragment)
        if fragment == "":
            return True
        return self._find_node(fragment) is not None

    def can_extend(self, fragment: str) -> bool:
        """Return whether at least one more letter can continue the fragment."""

        fragment = self.normalize_fragment(fragment)
        node = self._find_node(fragment)
        return bool(node and node.children)

    def is_completed_word(self, fragment: str) -> bool:
        """Return whether the fragment is a losing completed word."""

        fragment = self.normalize_fragment(fragment)
        return fragment in self.playable_words

    def next_letters(self, fragment: str) -> list[str]:
        """Return letters that keep the fragment on a playable-word path."""

        fragment = self.normalize_fragment(fragment)
        node = self._find_node(fragment)
        if node is None:
            return []
        return sorted(node.children)

    def outcome(self, fragment: str) -> Outcome:
        """Return the perfect-play result from the current player's turn."""

        fragment = self.normalize_fragment(fragment)
        return self._outcome(fragment)

    @lru_cache(maxsize=None)
    def _outcome(self, fragment: str) -> Outcome:
        if fragment and not self.is_prefix(fragment):
            return Outcome(is_winning=True, plies_to_end=0)
        if self.is_completed_word(fragment):
            return Outcome(is_winning=True, plies_to_end=0)

        winning_lengths: list[int] = []
        losing_lengths: list[int] = [1]

        for letter in self.next_letters(fragment):
            next_fragment = fragment + letter
            if self.is_completed_word(next_fragment):
                losing_lengths.append(1)
                continue
            if not self.can_extend(next_fragment):
                losing_lengths.append(1)
                continue

            child_outcome = self._outcome(next_fragment)
            plies_to_end = child_outcome.plies_to_end + 1
            if child_outcome.is_winning:
                losing_lengths.append(plies_to_end)
            else:
                winning_lengths.append(plies_to_end)

        if winning_lengths:
            return Outcome(is_winning=True, plies_to_end=min(winning_lengths))
        return Outcome(is_winning=False, plies_to_end=max(losing_lengths))

    def evaluate_move(self, fragment: str, letter: str) -> MoveEvaluation:
        """Evaluate adding one letter to the fragment."""

        fragment = self.normalize_fragment(fragment)
        letter = self.normalize_letter(letter)
        next_fragment = fragment + letter

        is_valid_prefix = self.is_prefix(next_fragment)
        completes_word = self.is_completed_word(next_fragment)
        can_be_extended = self.can_extend(next_fragment)

        if not is_valid_prefix:
            return MoveEvaluation(
                letter=letter,
                resulting_fragment=next_fragment,
                is_valid_prefix=False,
                completes_word=False,
                can_be_extended=False,
                is_safe=False,
                is_winning=False,
                plies_to_end=1,
                reason=(
                    f"adding '{letter}' creates \"{next_fragment}\", "
                    "which is not a prefix of any playable word"
                ),
            )

        if completes_word:
            return MoveEvaluation(
                letter=letter,
                resulting_fragment=next_fragment,
                is_valid_prefix=True,
                completes_word=True,
                can_be_extended=can_be_extended,
                is_safe=False,
                is_winning=False,
                plies_to_end=1,
                reason=(
                    f"adding '{letter}' forms \"{next_fragment}\", "
                    f"a complete word of length {len(next_fragment)}"
                ),
            )

        if not can_be_extended:
            return MoveEvaluation(
                letter=letter,
                resulting_fragment=next_fragment,
                is_valid_prefix=True,
                completes_word=False,
                can_be_extended=False,
                is_safe=False,
                is_winning=False,
                plies_to_end=1,
                reason=(
                    f"adding '{letter}' creates \"{next_fragment}\", "
                    "which cannot be extended to any playable word"
                ),
            )

        child_outcome = self.outcome(next_fragment)
        is_winning = not child_outcome.is_winning
        plies_to_end = child_outcome.plies_to_end + 1
        if is_winning:
            reason = (
                f"adding '{letter}' leaves \"{next_fragment}\" as a losing "
                "position for the opponent"
            )
        else:
            reason = (
                f"adding '{letter}' keeps \"{next_fragment}\" valid, but the "
                "opponent can force a win"
            )

        return MoveEvaluation(
            letter=letter,
            resulting_fragment=next_fragment,
            is_valid_prefix=True,
            completes_word=False,
            can_be_extended=True,
            is_safe=True,
            is_winning=is_winning,
            plies_to_end=plies_to_end,
            reason=reason,
        )

    def analyze_moves(
        self, fragment: str, include_invalid: bool = False
    ) -> list[MoveEvaluation]:
        """Return evaluated moves from a fragment.

        By default this only returns continuations present in the trie. Set
        include_invalid=True to classify every letter a-z, including dead
        prefixes that immediately lose.
        """

        fragment = self.normalize_fragment(fragment)
        letters = ALPHABET if include_invalid else self.next_letters(fragment)
        return [self.evaluate_move(fragment, letter) for letter in letters]

    def winning_moves(self, fragment: str) -> list[MoveEvaluation]:
        """Return safe moves that force a win for the mover."""

        return [
            move
            for move in self.analyze_moves(fragment)
            if move.is_safe and move.is_winning
        ]

    def losing_moves(self, fragment: str) -> list[MoveEvaluation]:
        """Return trie continuations that lose immediately or by force."""

        return [
            move
            for move in self.analyze_moves(fragment)
            if not (move.is_safe and move.is_winning)
        ]

    def status(self, fragment: str) -> str:
        """Return a compact status label for the current fragment."""

        fragment = self.normalize_fragment(fragment)
        if fragment and not self.is_prefix(fragment):
            return "invalid fragment"
        if self.is_completed_word(fragment):
            return "previous player completed a word"
        outcome = self.outcome(fragment)
        return "winning position" if outcome.is_winning else "losing position"

    def recommend(self, fragment: str) -> Recommendation:
        """Recommend the best action with a human-readable explanation."""

        fragment = self.normalize_fragment(fragment)

        if fragment and not self.is_prefix(fragment):
            return Recommendation(
                action="challenge",
                letter=None,
                resulting_fragment=fragment,
                status="invalid fragment",
                plies_to_end=0,
                reason=(
                    f"\"{fragment}\" is not a prefix of any playable word in "
                    "this dictionary"
                ),
            )

        if self.is_completed_word(fragment):
            return Recommendation(
                action="call_loss",
                letter=None,
                resulting_fragment=fragment,
                status="previous player completed a word",
                plies_to_end=0,
                reason=(
                    f"\"{fragment}\" is a complete word of length "
                    f"{len(fragment)}, so the previous move lost"
                ),
            )

        moves = self.analyze_moves(fragment)
        winning = [move for move in moves if move.is_safe and move.is_winning]
        safe_losing = [
            move for move in moves if move.is_safe and not move.is_winning
        ]

        if winning:
            best = min(winning, key=lambda move: (move.plies_to_end, move.letter))
            return Recommendation(
                action="play",
                letter=best.letter,
                resulting_fragment=best.resulting_fragment,
                status="winning position",
                plies_to_end=best.plies_to_end,
                reason=(
                    f"{best.reason}; all opponent responses eventually lose "
                    "with perfect play"
                ),
            )

        if safe_losing:
            best = min(
                safe_losing, key=lambda move: (-move.plies_to_end, move.letter)
            )
            return Recommendation(
                action="play",
                letter=best.letter,
                resulting_fragment=best.resulting_fragment,
                status="losing position",
                plies_to_end=best.plies_to_end,
                reason=(
                    "no winning move exists; "
                    f"{best.reason}, and it delays the forced loss the longest"
                ),
            )

        return Recommendation(
            action="no_safe_move",
            letter=None,
            resulting_fragment=fragment,
            status="losing position",
            plies_to_end=1,
            reason=self._no_safe_move_reason(fragment, moves),
        )

    def forced_losing_move(self, fragment: str) -> MoveEvaluation:
        """Return a deterministic move when every available move loses."""

        fragment = self.normalize_fragment(fragment)
        moves = self.analyze_moves(fragment)
        if moves:
            return min(moves, key=lambda move: (move.plies_to_end, move.letter))
        return self.evaluate_move(fragment, "a")

    def _no_safe_move_reason(
        self, fragment: str, moves: list[MoveEvaluation]
    ) -> str:
        if not moves:
            return "no letter keeps the fragment as a valid playable prefix"

        completed = [move for move in moves if move.completes_word]
        dead = [
            move
            for move in moves
            if not move.completes_word and not move.can_be_extended
        ]

        if len(moves) == 1 and completed:
            move = completed[0]
            return (
                f"adding '{move.letter}' forms \"{move.resulting_fragment}\", "
                f"a complete word of length {len(move.resulting_fragment)}, "
                "and no other continuation is valid"
            )

        if completed and len(completed) == len(moves):
            words = ", ".join(f"\"{move.resulting_fragment}\"" for move in completed)
            return f"every valid continuation completes a word: {words}"

        if dead and len(dead) == len(moves):
            return "every valid continuation creates a fragment that cannot continue"

        return "every continuation loses immediately"


def format_fragment(fragment: str) -> str:
    """Return a display string for a fragment."""

    return fragment if fragment else "(empty)"


def format_move_list(moves: list[MoveEvaluation]) -> str:
    """Format move evaluations for CLI output."""

    if not moves:
        return "none"

    parts = []
    for move in moves:
        if move.completes_word:
            parts.append(f"{move.letter} (forms \"{move.resulting_fragment}\")")
        elif not move.is_valid_prefix:
            parts.append(f"{move.letter} (dead prefix)")
        elif not move.can_be_extended:
            parts.append(f"{move.letter} (cannot be extended)")
        elif move.is_winning:
            parts.append(f"{move.letter} ({move.plies_to_end} plies)")
        else:
            parts.append(f"{move.letter} ({move.plies_to_end} plies)")
    return ", ".join(parts)


def print_analysis(
    solver: GhostSolver, fragment: str, show_invalid: bool = False
) -> None:
    """Print one-shot CLI analysis for a fragment."""

    fragment = solver.normalize_fragment(fragment)
    recommendation = solver.recommend(fragment)

    print(f"Current fragment: {format_fragment(fragment)}")
    print(f"Status: {recommendation.status}")
    print(f"Best action: {recommendation.action_text}")
    print(f"Reason: {recommendation.reason}")

    if recommendation.action in {"challenge", "call_loss"}:
        return

    moves = solver.analyze_moves(fragment, include_invalid=show_invalid)
    winning = [move for move in moves if move.is_safe and move.is_winning]
    losing = [move for move in moves if not (move.is_safe and move.is_winning)]
    print(f"Winning moves: {format_move_list(winning)}")
    print(f"Losing moves: {format_move_list(losing)}")


def load_solver_or_exit(path: str) -> GhostSolver:
    """Load a dictionary, printing a CLI-friendly error on failure."""

    try:
        solver = GhostSolver.from_file(path)
    except OSError as exc:
        print(f"error: could not read dictionary {path!r}: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    if not solver.playable_words:
        print(
            "error: dictionary contains no playable words of length 4 or more",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return solver


def bot_turn(solver: GhostSolver, fragment: str) -> tuple[str, bool]:
    """Make one bot move. Return the new fragment and whether play should end."""

    recommendation = solver.recommend(fragment)

    if recommendation.action == "challenge":
        print(
            f'Bot challenges: "{fragment}" is not a valid prefix in this dictionary'
        )
        return fragment, True

    if recommendation.action == "call_loss":
        print(
            f'Bot calls loss: "{fragment}" is a complete word of length '
            f"{len(fragment)}"
        )
        return fragment, True

    if recommendation.action == "play" and recommendation.letter is not None:
        move = solver.evaluate_move(fragment, recommendation.letter)
        print(f"Bot: {move.letter}")
        print(f"Reason: {recommendation.reason}")
        return move.resulting_fragment, False

    forced = solver.forced_losing_move(fragment)
    print("Bot has no safe move.")
    print(f"Bot: {forced.letter}")
    if forced.completes_word:
        print(
            f'Bot loses: "{forced.resulting_fragment}" is a complete word of '
            f"length {len(forced.resulting_fragment)}"
        )
    elif not forced.is_valid_prefix:
        print(
            f'Bot loses: "{forced.resulting_fragment}" is not a valid prefix '
            "in this dictionary"
        )
    else:
        print(
            f'Bot loses: "{forced.resulting_fragment}" cannot be extended to '
            "any playable word"
        )
    return forced.resulting_fragment, True


def interactive_game(solver: GhostSolver, fragment: str, bot_first: bool) -> None:
    """Run an interactive game against the bot."""

    fragment = solver.normalize_fragment(fragment)
    print(f"Current fragment: {format_fragment(fragment)}")
    print('Enter one letter, "challenge", "call", or "quit".')

    if bot_first:
        fragment, finished = bot_turn(solver, fragment)
        if finished:
            return
        print(f"Current fragment: {format_fragment(fragment)}")

    while True:
        raw_move = input("You: ").strip().lower()
        if raw_move in {"quit", "exit"}:
            print("Goodbye.")
            return

        if raw_move == "challenge":
            if fragment and not solver.is_prefix(fragment):
                print(
                    f'Challenge succeeds: "{fragment}" is not a valid prefix. '
                    "You win."
                )
            else:
                print(
                    f'Challenge fails: "{format_fragment(fragment)}" is a valid '
                    "prefix. You lose."
                )
            return

        if raw_move in {"call", "loss", "call loss"}:
            if solver.is_completed_word(fragment):
                print(
                    f'Call succeeds: "{fragment}" is a complete word of length '
                    f"{len(fragment)}. You win."
                )
            else:
                print(
                    f'Call fails: "{format_fragment(fragment)}" is not a '
                    "completed losing word. You lose."
                )
            return

        try:
            letter = solver.normalize_letter(raw_move)
        except ValueError:
            print('Enter exactly one letter, "challenge", "call", or "quit".')
            continue

        move = solver.evaluate_move(fragment, letter)
        fragment = move.resulting_fragment

        if move.completes_word:
            print(
                f'Bot calls loss: "{fragment}" is a complete word of length '
                f"{len(fragment)}"
            )
            print("You lose.")
            return

        if not move.is_valid_prefix:
            print(
                f'Bot challenges: "{fragment}" is not a valid prefix in this '
                "dictionary"
            )
            print("You lose.")
            return

        if not move.can_be_extended:
            print(
                f'Bot challenges: "{fragment}" cannot be extended to any '
                "playable word"
            )
            print("You lose.")
            return

        print(f"Current fragment: {format_fragment(fragment)}")
        fragment, finished = bot_turn(solver, fragment)
        if finished:
            return
        print(f"Current fragment: {format_fragment(fragment)}")


def build_arg_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""

    parser = argparse.ArgumentParser(
        description="Play or analyze the word game Ghost optimally."
    )
    parser.add_argument(
        "--dict",
        required=True,
        dest="dictionary",
        help="path to a dictionary file with one word per line",
    )
    parser.add_argument(
        "--fragment",
        default="",
        help="starting fragment to analyze or continue from",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="play interactively against the bot",
    )
    parser.add_argument(
        "--bot-first",
        action="store_true",
        help="in interactive mode, let the bot make the next move first",
    )
    parser.add_argument(
        "--show-invalid",
        action="store_true",
        help="include all invalid one-letter moves in one-shot analysis",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point."""

    parser = build_arg_parser()
    args = parser.parse_args(argv)
    solver = load_solver_or_exit(args.dictionary)

    try:
        fragment = solver.normalize_fragment(args.fragment)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.interactive:
        interactive_game(solver, fragment, args.bot_first)
    else:
        print_analysis(solver, fragment, show_invalid=args.show_invalid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
