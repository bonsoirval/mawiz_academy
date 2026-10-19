#!/usr/bin/env python3
"""Create a deployable copy of Python source without line comments.

Notes
-----
The script deliberately writes to a separate directory, never modifies the working
tree, and uses Python's tokenizer so hashes inside strings (URLs, templates, etc.)
remain untouched. Docstrings are preserved because they are runtime metadata, not
comments. Review and test the generated directory before deploying it.
"""

import argparse
import shutil
import tokenize
from pathlib import Path


EXCLUDED_DIRECTORIES = {".git", ".venv", "__pycache__", "instance", ".pytest_cache"}


def strip_python_comments(source: Path, destination: Path) -> None:
    """Copy one Python file while omitting COMMENT tokens.

    Parameters
    ----------
    source : pathlib.Path
        Existing Python source file.
    destination : pathlib.Path
        File path for the stripped copy. Its parent must already exist.
    """
    with tokenize.open(source) as handle:
        tokens = list(tokenize.generate_tokens(handle.readline))
    kept = [token for token in tokens if token.type != tokenize.COMMENT]
    rendered = tokenize.untokenize(kept)
    destination.write_text("\n".join(line.rstrip() for line in rendered.splitlines()) + "\n", encoding="utf-8")


def copy_for_deployment(source_root: Path, output_root: Path) -> None:
    """Copy a project while stripping comments only from Python files.

    Parameters
    ----------
    source_root : pathlib.Path
        Existing project directory.
    output_root : pathlib.Path
        Empty destination directory outside the project tree.

    Notes
    -----
    Non-Python assets are copied byte-for-byte. Runtime state and dependency
    directories listed in EXCLUDED_DIRECTORIES are deliberately omitted.
    """
    for source in source_root.rglob("*"):
        if any(part in EXCLUDED_DIRECTORIES for part in source.relative_to(source_root).parts):
            continue
        relative = source.relative_to(source_root)
        destination = output_root / relative
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif source.suffix == ".py":
            destination.parent.mkdir(parents=True, exist_ok=True)
            strip_python_comments(source, destination)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)


def main() -> None:
    """Parse command-line options and create a safe deployment copy.

    Raises
    ------
    SystemExit
        If the source is missing, output is unsafe, or output is non-empty.
    """
    parser = argparse.ArgumentParser(description="Create a deployment copy without Python comments.")
    parser.add_argument("--source", type=Path, default=Path.cwd(), help="Project directory to copy (default: current directory).")
    parser.add_argument("--output", type=Path, required=True, help="New, empty destination directory.")
    args = parser.parse_args()
    source_root = args.source.resolve()
    output_root = args.output.resolve()
    if not source_root.is_dir():
        parser.error(f"Source directory does not exist: {source_root}")
    if output_root == source_root or source_root in output_root.parents:
        parser.error("Output must be outside the source directory.")
    if output_root.exists() and any(output_root.iterdir()):
        parser.error(f"Output directory must be empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    copy_for_deployment(source_root, output_root)
    print(f"Deployment copy created at {output_root}")


if __name__ == "__main__":
    main()
