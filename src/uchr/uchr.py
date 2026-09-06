#!/usr/bin/env python3

import argparse
import io
import sys


def wrap_io():
    """Wrap stdin/stdout/stderr with UTF-8 encoding"""
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", line_buffering=True
    )
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", line_buffering=True
    )


def search_command(args):
    """Handle uchr search subcommand"""
    from .search import search

    # Convert args to match search.search signature
    by = args.by if args.by else "name"

    if (by == "code" or by == "char") and args.strict:
        print(f"warning: Ignore --strict in {by} search")

    search(
        args.expression,
        by,
        args.delimiter,
        strict=args.strict,
        first=args.first,
        format=args.format,
    )


def normalize_command(args):
    """Handle uchr normalize subcommand"""
    from .normalize import normalize_command as normalize_func

    return normalize_func(
        form=args.form,
        halfwidth=args.halfwidth,
        compare=args.compare,
        detailed=args.detail,
        delimiter=args.delimiter,
        input_file=args.input_file,
    )


def db_create_command(args):
    """Handle uchr db create subcommand"""
    from .database import create_database

    return create_database()


def db_delete_command(args):
    """Handle uchr db delete subcommand"""
    from .database import delete_database

    return delete_database()


def db_info_command(args):
    """Handle uchr db info subcommand"""
    from .database import database_info

    return database_info()


def create_parser():
    """Create the main argument parser with subcommands"""
    parser = argparse.ArgumentParser(
        prog="uchr",
        description="Unicode character tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uchr search ghost                    # Search for characters named 'ghost'
  uchr search -c 1F47A-1F480          # Search by code range
  uchr search -x 👻                   # Search by character
  uchr search -b "Emoticons"          # Search by Unicode block
  uchr normalize                      # Normalize text from stdin (NFC)
  uchr normalize --form nfd           # Normalize to NFD form
  uchr normalize --halfwidth          # Convert fullwidth to halfwidth
  uchr normalize --detail             # Show result form binary unicode
  uchr normalize --compare            # Show all normalization forms
  uchr db create                      # Create Unicode database
  uchr db info                        # Show database location
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Search subcommand
    search_parser = subparsers.add_parser("search", help="Search Unicode characters")
    search_parser.add_argument(
        "expression", metavar="EXPR", help="Expression to search"
    )

    search_by_group = search_parser.add_mutually_exclusive_group()
    search_by_group.add_argument(
        "-b",
        "--block",
        action="store_const",
        dest="by",
        const="block",
        help="Search by block name",
    )
    search_by_group.add_argument(
        "-c",
        "--code",
        action="store_const",
        dest="by",
        const="code",
        help="Search by code point or range",
    )
    search_by_group.add_argument(
        "-x",
        "--char",
        action="store_const",
        dest="by",
        const="char",
        help="Search by character",
    )
    search_by_group.add_argument(
        "-d",
        "--detail",
        action="store_const",
        dest="by",
        const="detail",
        help="Search by character details",
    )

    search_parser.add_argument(
        "-s",
        "--strict",
        action="store_true",
        help="Match name strictly (case insensitive)",
    )
    search_parser.add_argument(
        "-1", "--first", action="store_true", help="Show first result only"
    )
    search_parser.add_argument(
        "-f", "--format", choices=["utf8", "simple"], default=None, help="Output format"
    )
    search_parser.add_argument(
        "-D", "--delimiter", default=" ", help="Output delimiter (default: space)"
    )
    search_parser.set_defaults(func=search_command)

    # Normalize subcommand
    normalize_parser = subparsers.add_parser(
        "normalize", help="Normalize and convert Unicode text"
    )
    normalize_parser.add_argument(
        "input_file", nargs="?", default=None, help="Input file (default: stdin)"
    )
    normalize_parser.add_argument(
        "--form",
        choices=["nfc", "nfd", "nfkc", "nfkd"],
        default="nfc",
        help="Unicode normalization form (default: nfc)",
    )
    normalize_parser.add_argument(
        "--halfwidth",
        action="store_true",
        help="Convert fullwidth characters to halfwidth",
    )
    normalize_parser.add_argument(
        "--compare",
        action="store_true",
        help="Show comparison of all normalization forms",
    )
    normalize_parser.add_argument(
        "--detail",
        action="store_true",
        help="Show detailed output: result form binary unicode",
    )
    normalize_parser.add_argument(
        "--delimiter",
        default=" ",
        help="Delimiter for detailed output (default: space)",
    )
    normalize_parser.set_defaults(func=normalize_command)

    # Database subcommand
    db_parser = subparsers.add_parser("db", help="Database management")
    db_subparsers = db_parser.add_subparsers(
        dest="db_command", help="Database operations"
    )

    # db create
    db_create_parser = db_subparsers.add_parser(
        "create", help="Create Unicode database"
    )
    db_create_parser.set_defaults(func=db_create_command)

    # db delete
    db_delete_parser = db_subparsers.add_parser(
        "delete", help="Delete Unicode database"
    )
    db_delete_parser.set_defaults(func=db_delete_command)

    # db info
    db_info_parser = db_subparsers.add_parser("info", help="Show database information")
    db_info_parser.set_defaults(func=db_info_command)

    return parser


def main():
    """Main entry point for uchr command"""
    wrap_io()

    parser = create_parser()
    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        return 1

    try:
        return args.func(args) or 0
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def uchr():
    """Entry point for console_scripts"""
    return main()


if __name__ == "__main__":
    sys.exit(main())
