#!/usr/bin/env python3

import argparse
import io
import os
import sys

# Exit status shells report for a process killed by SIGPIPE (128 + 13),
# which is what standard tools return when the reader of a pipe goes away.
EXIT_BROKEN_PIPE = 141


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
    from .database import resolve_search_version
    from .search import search

    version, error = resolve_search_version(args.unicode_version)
    if error:
        print(error, file=sys.stderr)
        return 1

    # Convert args to match search.search signature
    by = args.by if args.by else "name"

    if (by == "code" or by == "char") and args.strict:
        print(f"warning: Ignore --strict in {by} search", file=sys.stderr)

    search(
        args.expression,
        by,
        args.delimiter,
        strict=args.strict,
        first=args.first,
        output_format=args.format,
        version=version,
    )


def normalize_command(args):
    """Handle uchr normalize subcommand"""
    import unicodedata

    from .normalize import normalize_command as normalize_func

    # normalize uses Python's built-in unicodedata, not the uchr DB, so it
    # cannot follow `uchr db` versions; it is kept only for compatibility.
    print(
        "warning: 'uchr normalize' is deprecated and will be removed in a "
        "future release. It uses the Unicode data built into Python "
        f"(Unicode {unicodedata.unidata_version}), not the uchr database.",
        file=sys.stderr,
    )

    return normalize_func(
        form=args.form,
        halfwidth=args.halfwidth,
        compare=args.compare,
        detailed=args.detail,
        delimiter=args.delimiter,
        input_file=args.input_file,
    )


def db_update_command(args):
    """Handle uchr db update subcommand"""
    from .database import update_database

    return update_database(version=args.version, verbose=args.verbose)


def db_use_command(args):
    """Handle uchr db use subcommand"""
    from .database import use_version

    return use_version(args.version)


def db_list_command(args):
    """Handle uchr db list subcommand"""
    from .database import list_versions

    return list_versions()


def db_delete_command(args):
    """Handle uchr db delete subcommand"""
    from .database import delete_version

    if not args.version and not args.all:
        print("Error: specify a version or --all", file=sys.stderr)
        return 1
    return delete_version(version=args.version, delete_all=args.all)


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
  uchr search ghost --unicode-version 16.0.0  # Search a specific version
  uchr db update                      # Fetch latest Unicode data
  uchr db update --version 16.0.0     # Fetch a specific version
  uchr db use 16.0.0                  # Switch current version
  uchr db list                        # List available/local versions
  uchr db delete 16.0.0               # Delete one version's data
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
    search_parser.add_argument(
        "--unicode-version",
        default=None,
        metavar="X.Y.Z",
        help="Search a specific Unicode version instead of the current one",
    )
    search_parser.set_defaults(func=search_command)

    # Normalize subcommand
    normalize_parser = subparsers.add_parser(
        "normalize",
        help="(deprecated) Normalize and convert Unicode text",
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

    # db update
    db_update_parser = db_subparsers.add_parser(
        "update", help="Fetch a Unicode version and set it as current"
    )
    db_update_parser.add_argument(
        "--version",
        default=None,
        metavar="X.Y.Z",
        help="Version to fetch (default: resolve latest from unicode.org)",
    )
    db_update_parser.add_argument(
        "--verbose",
        action="store_true",
        help="List every skipped code point, range and duplicate emoji",
    )
    db_update_parser.set_defaults(func=db_update_command)

    # db use
    db_use_parser = db_subparsers.add_parser(
        "use", help="Switch current version to one already stored locally"
    )
    db_use_parser.add_argument("version", metavar="X.Y.Z", help="Version to switch to")
    db_use_parser.set_defaults(func=db_use_command)

    # db list
    db_list_parser = db_subparsers.add_parser(
        "list", help="List published and locally stored Unicode versions"
    )
    db_list_parser.set_defaults(func=db_list_command)

    # db delete
    db_delete_parser = db_subparsers.add_parser(
        "delete", help="Delete one version's data, or all data"
    )
    db_delete_parser.add_argument(
        "version", metavar="X.Y.Z", nargs="?", default=None, help="Version to delete"
    )
    db_delete_parser.add_argument(
        "--all", action="store_true", help="Delete the entire database file"
    )
    db_delete_parser.set_defaults(func=db_delete_command)

    return parser


def quiet_broken_pipe():
    """Handle a closed stdout pipe (e.g. `uchr search ... | head -1`).

    Exit quietly like other Unix tools. stdout is pointed at /dev/null so
    the final flush at interpreter shutdown doesn't raise BrokenPipeError
    again (the approach recommended in the Python `signal` docs).
    """
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, sys.stdout.fileno())
    return EXIT_BROKEN_PIPE


def main():
    """Main entry point for uchr command"""
    wrap_io()

    parser = create_parser()
    try:
        try:
            args = parser.parse_args()
        except SystemExit as e:  # after --help or a usage error
            status = e.code
        else:
            if hasattr(args, "func"):
                status = args.func(args) or 0
            else:
                parser.print_help()
                status = 1
        # Flush here so a closed pipe is handled below instead of surfacing
        # as an "Exception ignored" message at interpreter shutdown.
        # (argparse ignores write errors, so only this flush notices them.)
        sys.stdout.flush()
        return status
    except BrokenPipeError:
        return quiet_broken_pipe()
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
