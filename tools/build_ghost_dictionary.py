#!/usr/bin/env python3
"""Build a Ghost-compatible dictionary from the bundled SCOWL database.

Examples:

    python tools/build_ghost_dictionary.py --output words.txt
    python tools/build_ghost_dictionary.py --size 70 --output words-large.txt
    python ghost_bot.py --dict words.txt --fragment dres

The output format is what ghost_bot.py expects: one lowercase ASCII alphabetic
word per line.  By default this also skips SCOWL entries that look like proper
nouns by excluding proper-name POS classes and rejecting any source entry that
is not already lowercase.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import unicodedata
from pathlib import Path
from typing import Iterable, TextIO


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "third_party" / "wordlist" / "scowl.db"
DEFAULT_SIZE = 60
DEFAULT_SPELLINGS = ("A",)
DEFAULT_VARIANT_LEVEL = 1
DEFAULT_MIN_LENGTH = 4

SPELLING_REGIONS = {
    "A": "US",
    "B": "GB",
    "Z": "GB",
    "C": "CA",
    "D": "AU",
}

PROPER_NOUN_POS_CLASSES = (
    "name",
    "name?",
    "person",
    "place",
    "surname",
    "trademark",
    "upper",
    "upper?",
)


def parse_csv(value: str) -> tuple[str, ...]:
    """Parse a comma-separated command-line value."""

    return tuple(item.strip().upper() for item in value.split(",") if item.strip())


def deaccent(word: str) -> str:
    """Return a best-effort ASCII-friendly version of an accented word."""

    decomposed = unicodedata.normalize("NFKD", word)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_for_ghost(
    raw_word: str,
    *,
    min_length: int,
    keep_capitalized: bool,
) -> str | None:
    """Normalize one SCOWL word, or return None if Ghost should not load it."""

    word = raw_word.strip()
    if not word:
        return None
    if not keep_capitalized and word != word.lower():
        return None

    normalized = deaccent(word).lower()
    if len(normalized) < min_length:
        return None
    if normalized.isascii() and normalized.isalpha():
        return normalized
    return None


def build_query(
    *,
    size: int,
    spellings: Iterable[str],
    variant_level: int,
    keep_proper_pos_classes: bool,
) -> tuple[str, list[object]]:
    """Build the SCOWL query and positional arguments."""

    spelling_codes = tuple(spellings)
    spelling_values = sorted({"_", *spelling_codes})
    regions = sorted({"", *(SPELLING_REGIONS[sp] for sp in spelling_codes)})

    clauses = [
        "size <= ?",
        "variant_level <= ?",
        f"spelling in ({','.join('?' for _ in spelling_values)})",
        f"region in ({','.join('?' for _ in regions)})",
        "category = ''",
        "pos_category = ''",
    ]
    params: list[object] = [size, variant_level, *spelling_values, *regions]

    if not keep_proper_pos_classes:
        clauses.append(
            f"pos_class not in ({','.join('?' for _ in PROPER_NOUN_POS_CLASSES)})"
        )
        params.extend(PROPER_NOUN_POS_CLASSES)

    query = f"""
        select distinct word
        from scowl_v0
        where {' and '.join(clauses)}
    """
    return query, params


def load_words(
    db_path: Path,
    *,
    size: int,
    spellings: Iterable[str],
    variant_level: int,
    min_length: int,
    keep_capitalized: bool,
    keep_proper_pos_classes: bool,
) -> set[str]:
    """Load and normalize matching SCOWL words."""

    query, params = build_query(
        size=size,
        spellings=spellings,
        variant_level=variant_level,
        keep_proper_pos_classes=keep_proper_pos_classes,
    )
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(query, params)
        words = {
            normalized
            for (raw_word,) in rows
            if (
                normalized := normalize_for_ghost(
                    raw_word,
                    min_length=min_length,
                    keep_capitalized=keep_capitalized,
                )
            )
            is not None
        }
    finally:
        conn.close()

    return words


def write_words(words: Iterable[str], output: TextIO) -> None:
    """Write sorted words, one per line."""

    for word in sorted(words):
        print(word, file=output)


def build_arg_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""

    parser = argparse.ArgumentParser(
        description="Convert the bundled SCOWL word list to Ghost format."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help=f"path to scowl.db (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="output path; stdout is used when omitted",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=DEFAULT_SIZE,
        help=f"maximum SCOWL size (default: {DEFAULT_SIZE})",
    )
    parser.add_argument(
        "--spellings",
        type=parse_csv,
        default=DEFAULT_SPELLINGS,
        help="comma-separated spelling codes: A,B,Z,C,D (default: A)",
    )
    parser.add_argument(
        "--variant-level",
        type=int,
        default=DEFAULT_VARIANT_LEVEL,
        help=f"maximum SCOWL variant level (default: {DEFAULT_VARIANT_LEVEL})",
    )
    parser.add_argument(
        "--min-length",
        type=int,
        default=DEFAULT_MIN_LENGTH,
        help=f"minimum output word length (default: {DEFAULT_MIN_LENGTH})",
    )
    parser.add_argument(
        "--keep-capitalized",
        action="store_true",
        help="keep entries whose source spelling is capitalized or mixed case",
    )
    parser.add_argument(
        "--keep-proper-pos-classes",
        action="store_true",
        help="do not exclude SCOWL POS classes used for names/proper nouns",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="print the number of emitted words to stderr",
    )
    return parser


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Validate arguments that argparse cannot express cleanly."""

    if not args.db.exists():
        parser.error(f"SCOWL database not found: {args.db}")
    if args.size < 0:
        parser.error("--size must be non-negative")
    if args.variant_level < 0:
        parser.error("--variant-level must be non-negative")
    if args.min_length < 1:
        parser.error("--min-length must be at least 1")

    invalid_spellings = sorted(set(args.spellings) - set(SPELLING_REGIONS))
    if invalid_spellings:
        parser.error(
            "--spellings contains unsupported code(s): "
            + ", ".join(invalid_spellings)
        )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""

    parser = build_arg_parser()
    args = parser.parse_args(argv)
    validate_args(parser, args)

    words = load_words(
        args.db,
        size=args.size,
        spellings=args.spellings,
        variant_level=args.variant_level,
        min_length=args.min_length,
        keep_capitalized=args.keep_capitalized,
        keep_proper_pos_classes=args.keep_proper_pos_classes,
    )

    if args.output is None:
        write_words(words, sys.stdout)
    else:
        with args.output.open("w", encoding="utf-8") as handle:
            write_words(words, handle)

    if args.summary:
        print(f"wrote {len(words)} words", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
