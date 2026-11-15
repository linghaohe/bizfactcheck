"""Local-only command-line entry points and exit-code policy."""

import argparse
from pathlib import Path
import sys

from .core import check_documents, verify_manifest
from .reports import render_report


_ERRORS = {
    "en": {
        "input": "Cannot read or validate the inputs. Check the file paths, supported formats and evidence manifest.",
        "exists": "Output path already exists; choose a new report path. Existing files and symlinks are never overwritten.",
        "input_output": "Output must not be an input path; choose a new report path.",
        "write": "Cannot write the report. Check the output directory and write permissions.",
    },
    "zh": {
        "input": "无法读取或校验输入。请检查文件路径、支持的格式和证据清单。",
        "exists": "输出路径已存在，请使用新的报告路径。不会覆盖已有文件或符号链接。",
        "input_output": "输出路径不能是输入文件，请使用新的报告路径。",
        "write": "无法写入报告，请检查输出目录和写入权限。",
    },
}


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse errors can echo arbitrary argument values, including secrets.
        self.print_usage(sys.stderr)
        self.exit(2, "bizfactcheck: invalid arguments; use --help for supported options.\n")


def _parser():
    parser = _Parser(
        prog="bizfactcheck",
        description="Compare listed business fields against local references. No model, account or network required.",
        epilog="Exit codes: 0 = listed comparisons consistent; 1 = differences or review; 2 = invalid input/output or no comparable pairs.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="compare labeled fields in local documents")
    check.add_argument("--source", required=True, type=Path, metavar="SOURCE", help="reference .md, .txt or .docx file")
    check.add_argument("--draft", required=True, nargs="+", type=Path, metavar="DRAFT", help="one or more draft files")
    verify = commands.add_parser("verify", help="check quoted evidence in a JSON manifest")
    verify.add_argument("manifest", type=Path, metavar="CHECKS.json", help="manifest; evidence paths are relative to this file")
    for command in (check, verify):
        command.add_argument("--lang", choices=("en", "zh"), default="en", help="report language (default: en)")
        command.add_argument("--format", choices=("text", "json", "md", "html"), default="text", help="report format (default: text)")
        command.add_argument("--output", type=Path, metavar="FILE", help="write to a new file; existing paths are refused")
    return parser


def _error(key, lang):
    print("bizfactcheck: " + _ERRORS[lang][key], file=sys.stderr)
    return 2


def main(argv=None) -> int:
    """Write the report, then return 0, 1 or 2 according to its coverage."""
    try:
        args = _parser().parse_args(argv)
    except SystemExit as error:
        return error.code

    try:
        if args.output and (args.output.exists() or args.output.is_symlink()):
            return _error("exists", args.lang)
    except OSError:
        return _error("write", args.lang)

    try:
        if args.command == "check":
            report = check_documents(args.source, args.draft)
        else:
            report = verify_manifest(args.manifest)
    except (OSError, ValueError, RuntimeError):
        # Never expose exception text: parsers and filesystem errors may include
        # document contents, raw input values or sensitive path components.
        return _error("input", args.lang)

    rendered = render_report(report, lang=args.lang, format=args.format)
    try:
        if args.output:
            inputs = {Path(path).resolve() for path in report["input_paths"]}
            if args.output.resolve() in inputs:
                return _error("input_output", args.lang)
            # Exclusive creation also protects against a file or symlink that
            # appears after the earlier check.
            with args.output.open("x", encoding="utf-8", newline="\n") as output:
                output.write(rendered + "\n")
        else:
            sys.stdout.write(rendered + "\n")
            sys.stdout.flush()
    except FileExistsError:
        return _error("exists", args.lang)
    except (OSError, ValueError, RuntimeError):
        return _error("write", args.lang)

    if report["coverage"]["compared"] == 0:
        return 2
    if any(finding["status"] in ("conflict", "review") for finding in report["findings"]):
        return 1
    return 0
