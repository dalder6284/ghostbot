#!/usr/bin/env python3
"""Export Ghost winning-strategy branches as a JSON DAG.

Examples:

    python tools/export_strategy_dag.py --dict words.txt --output strategy.json
    python tools/export_strategy_dag.py --dict words.txt --root-moves h,j,m,r
    python tools/export_strategy_dag.py --dict words.txt --mode second-player
    python tools/export_strategy_dag.py --dict words.txt --fragment tr --max-depth 5

The graph is a proof certificate for one or more winning moves.  Opponent-turn
losing nodes expand every valid continuation.  Bot-turn winning nodes expand
only the selected strategy move, because one winning reply is enough to prove
that position.
"""

from __future__ import annotations

import argparse
import json
import string
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from ghost_bot import GhostSolver, MoveEvaluation  # noqa: E402


ALPHABET = string.ascii_lowercase


def parse_csv(value: str) -> list[str]:
    """Parse a comma-separated list."""

    return [item.strip().lower() for item in value.split(",") if item.strip()]


def node_id(fragment: str) -> str:
    """Return a stable JSON graph id for a fragment."""

    return f"f:{fragment}"


def move_to_dict(move: MoveEvaluation) -> dict[str, Any]:
    """Serialize a MoveEvaluation without exposing Python internals."""

    return asdict(move)


class StrategyDagExporter:
    """Build a proof DAG for Ghost winning strategies."""

    def __init__(
        self,
        solver: GhostSolver,
        *,
        start_fragment: str,
        root_moves: Iterable[str],
        dictionary_path: Path,
        max_depth: Optional[int],
        include_invalid_edges: bool,
        start_mover: str = "bot",
    ) -> None:
        self.solver = solver
        self.start_fragment = start_fragment
        self.root_moves = list(root_moves)
        self.dictionary_path = dictionary_path
        self.max_depth = max_depth
        self.include_invalid_edges = include_invalid_edges
        self.start_mover = start_mover
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, Any]] = []
        self.expanded: set[str] = set()

    def export(self) -> dict[str, Any]:
        """Return the complete DAG document."""

        self._add_node(self.start_fragment)
        for letter in self.root_moves:
            move = self.solver.evaluate_move(self.start_fragment, letter)
            if not (move.is_safe and move.is_winning):
                raise ValueError(
                    f"root move {letter!r} is not a winning move from "
                    f"{self.start_fragment!r}"
                )
            self._add_edge(
                self.start_fragment,
                move.resulting_fragment,
                move,
                kind="root_choice",
                mover=self._mover_for_fragment(self.start_fragment),
            )
            self._expand_losing_node(move.resulting_fragment)

        return self._document(mode="first_player")

    def export_second_player_response(self) -> dict[str, Any]:
        """Return a DAG proving bot wins after opponent's losing opener."""

        self._add_node(self.start_fragment)
        for letter in self.root_moves:
            move = self.solver.evaluate_move(self.start_fragment, letter)
            if move.is_safe and move.is_winning:
                raise ValueError(
                    f"opponent root move {letter!r} is a winning move from "
                    f"{self.start_fragment!r}; it cannot be forced against"
                )
            self._add_edge(
                self.start_fragment,
                move.resulting_fragment,
                move,
                kind="opponent_opening",
                mover=self._mover_for_fragment(self.start_fragment),
            )
            if move.is_safe:
                self._expand_winning_node(move.resulting_fragment)

        return self._document(mode="second_player_response")

    def _document(self, *, mode: str) -> dict[str, Any]:
        """Return the complete DAG document."""

        return {
            "schema_version": 1,
            "mode": mode,
            "dictionary": str(self.dictionary_path),
            "start_fragment": self.start_fragment,
            "start_mover": self.start_mover,
            "root_moves": self.root_moves,
            "max_depth": self.max_depth,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "nodes": sorted(self.nodes.values(), key=lambda node: node["id"]),
            "edges": self.edges,
        }

    def _relative_depth(self, fragment: str) -> int:
        return len(fragment) - len(self.start_fragment)

    def _depth_limited(self, fragment: str) -> bool:
        return (
            self.max_depth is not None
            and self._relative_depth(fragment) >= self.max_depth
        )

    def _mover_for_fragment(self, fragment: str) -> str:
        if self._relative_depth(fragment) % 2 == 0:
            return self.start_mover
        return "opponent" if self.start_mover == "bot" else "bot"

    def _status_for_fragment(self, fragment: str) -> str:
        if fragment and not self.solver.is_prefix(fragment):
            return "invalid_fragment"
        if self.solver.is_completed_word(fragment):
            return "completed_word"
        if not self.solver.can_extend(fragment):
            return "dead_prefix"
        return "winning" if self.solver.outcome(fragment).is_winning else "losing"

    def _invalid_letters(self, fragment: str) -> list[str]:
        valid = set(self.solver.next_letters(fragment))
        return [letter for letter in ALPHABET if letter not in valid]

    def _add_node(
        self,
        fragment: str,
        *,
        terminal_reason: Optional[str] = None,
        losing_mover: Optional[str] = None,
    ) -> None:
        nid = node_id(fragment)
        if nid in self.nodes:
            if terminal_reason and not self.nodes[nid].get("terminal_reason"):
                self.nodes[nid]["terminal"] = True
                self.nodes[nid]["terminal_reason"] = terminal_reason
                self.nodes[nid]["losing_mover"] = losing_mover
            return

        is_terminal = terminal_reason is not None
        valid_letters = [] if is_terminal else self.solver.next_letters(fragment)
        invalid_letters = [] if is_terminal else self._invalid_letters(fragment)
        outcome = None if is_terminal else self.solver.outcome(fragment)
        self.nodes[nid] = {
            "id": nid,
            "fragment": fragment,
            "label": fragment if fragment else "(empty)",
            "depth": self._relative_depth(fragment),
            "turn": None if is_terminal else self._mover_for_fragment(fragment),
            "status": terminal_reason or self._status_for_fragment(fragment),
            "terminal": is_terminal,
            "terminal_reason": terminal_reason,
            "losing_mover": losing_mover,
            "is_winning_for_player_to_move": (
                None if outcome is None else outcome.is_winning
            ),
            "plies_to_end": None if outcome is None else outcome.plies_to_end,
            "valid_letters": valid_letters,
            "invalid_letters": invalid_letters,
            "truncated": False,
        }

    def _mark_truncated(self, fragment: str) -> None:
        node = self.nodes[node_id(fragment)]
        node["truncated"] = True
        node["status"] = f"{node['status']}_truncated"

    def _add_edge(
        self,
        source: str,
        target: str,
        move: MoveEvaluation,
        *,
        kind: str,
        mover: str,
    ) -> None:
        terminal_reason = self._terminal_reason(move)
        self._add_node(
            target,
            terminal_reason=terminal_reason,
            losing_mover=mover if terminal_reason else None,
        )
        self.edges.append(
            {
                "source": node_id(source),
                "target": node_id(target),
                "letter": move.letter,
                "kind": kind,
                "mover": mover,
                "is_strategy": kind in {"root_choice", "strategy_reply"},
                "move": move_to_dict(move),
            }
        )

    def _add_invalid_edges(self, fragment: str) -> None:
        if not self.include_invalid_edges:
            return

        mover = self._mover_for_fragment(fragment)
        for letter in self._invalid_letters(fragment):
            move = self.solver.evaluate_move(fragment, letter)
            self._add_edge(
                fragment,
                move.resulting_fragment,
                move,
                kind="invalid_immediate_loss",
                mover=mover,
            )

    def _terminal_reason(self, move: MoveEvaluation) -> Optional[str]:
        if move.is_safe:
            return None
        if not move.is_valid_prefix:
            return "invalid_prefix"
        if move.completes_word:
            return "completed_word"
        if not move.can_be_extended:
            return "dead_prefix"
        return "immediate_loss"

    def _expand_losing_node(self, fragment: str) -> None:
        self._add_node(fragment)
        if self._depth_limited(fragment):
            self._mark_truncated(fragment)
            return

        nid = node_id(fragment)
        if nid in self.expanded:
            return
        self.expanded.add(nid)

        self._add_invalid_edges(fragment)
        for move in self.solver.analyze_moves(fragment):
            self._add_edge(
                fragment,
                move.resulting_fragment,
                move,
                kind="opponent_option",
                mover=self._mover_for_fragment(fragment),
            )
            if move.is_safe:
                self._expand_winning_node(move.resulting_fragment)

    def _expand_winning_node(self, fragment: str) -> None:
        self._add_node(fragment)
        if self._depth_limited(fragment):
            self._mark_truncated(fragment)
            return

        nid = node_id(fragment)
        if nid in self.expanded:
            return
        self.expanded.add(nid)

        move = self._choose_strategy_move(fragment)
        self._add_edge(
            fragment,
            move.resulting_fragment,
            move,
            kind="strategy_reply",
            mover=self._mover_for_fragment(fragment),
        )
        if move.is_safe:
            self._expand_losing_node(move.resulting_fragment)

    def _choose_strategy_move(self, fragment: str) -> MoveEvaluation:
        winning = self.solver.winning_moves(fragment)
        if not winning:
            raise ValueError(f"{fragment!r} is not a winning position")
        return min(winning, key=lambda move: (move.plies_to_end, move.letter))


def find_root_moves(
    solver: GhostSolver,
    fragment: str,
    explicit_moves: Optional[list[str]],
    *,
    mode: str,
) -> list[str]:
    """Return root moves to export."""

    if explicit_moves is not None:
        moves = explicit_moves
    elif mode == "first-player":
        moves = [move.letter for move in solver.winning_moves(fragment)]
    else:
        moves = [
            move.letter
            for move in solver.analyze_moves(fragment)
            if move.is_safe and not move.is_winning
        ]
    if not moves:
        raise ValueError(f"no root moves found from {fragment!r}")
    return moves


def build_arg_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""

    parser = argparse.ArgumentParser(
        description="Export Ghost winning-strategy branches as JSON."
    )
    parser.add_argument(
        "--dict",
        required=True,
        dest="dictionary",
        type=Path,
        help="path to the Ghost dictionary file",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="output JSON path; stdout is used when omitted",
    )
    parser.add_argument(
        "--fragment",
        default="",
        help="starting fragment; defaults to the empty opening position",
    )
    parser.add_argument(
        "--root-moves",
        type=parse_csv,
        help=(
            "comma-separated root moves to export; defaults to all winning "
            "moves in first-player mode or all losing openers in second-player mode"
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("first-player", "second-player"),
        default="first-player",
        help=(
            "first-player exports winning root choices; second-player exports "
            "opponent losing openers plus bot replies"
        ),
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        help="optional maximum depth from the starting fragment",
    )
    parser.add_argument(
        "--include-invalid-edges",
        action="store_true",
        help="expand invalid letters as terminal edges instead of summaries only",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation; use 0 for compact output",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="print node/edge counts to stderr",
    )
    return parser


def write_json(document: dict[str, Any], output: Any, indent: int) -> None:
    """Write the graph document as JSON."""

    if indent <= 0:
        json.dump(document, output, separators=(",", ":"))
    else:
        json.dump(document, output, indent=indent)
    output.write("\n")


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point."""

    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.max_depth is not None and args.max_depth < 1:
        parser.error("--max-depth must be at least 1")

    try:
        solver = GhostSolver.from_file(args.dictionary)
        fragment = solver.normalize_fragment(args.fragment)
        root_moves = find_root_moves(
            solver, fragment, args.root_moves, mode=args.mode
        )
        exporter = StrategyDagExporter(
            solver,
            start_fragment=fragment,
            root_moves=root_moves,
            dictionary_path=args.dictionary,
            max_depth=args.max_depth,
            include_invalid_edges=args.include_invalid_edges,
            start_mover="bot" if args.mode == "first-player" else "opponent",
        )
        if args.mode == "first-player":
            document = exporter.export()
        else:
            document = exporter.export_second_player_response()
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.output is None:
        write_json(document, sys.stdout, args.indent)
    else:
        with args.output.open("w", encoding="utf-8") as handle:
            write_json(document, handle, args.indent)

    if args.summary:
        print(
            f"exported {document['node_count']} nodes and "
            f"{document['edge_count']} edges",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
