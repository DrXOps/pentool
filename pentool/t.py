#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script to bundle the project into a single text file.
Collects all text files (by extension and known names),
ignoring service folders (__pycache__, .git, node_modules, etc.).
The result is saved to the specified file with headers for each source file.

After creation, stats are printed:
- file size on disk
- character count
- approximate token count (characters / 4)
- warning if tokens > 128k
"""

import os
import sys
import argparse
from pathlib import Path

# Directories to be fully excluded from traversal
EXCLUDE_DIRS = {
    '.git', '__pycache__', 'node_modules', '.venv', 'venv', 'env',
    'dist', 'build', '.idea', '.vscode', '.pytest_cache', '.mypy_cache',
    '.tox', '.eggs', 'coverage', 'htmlcov', '.ruff_cache', '.ipynb_checkpoints'
}

# File extensions considered as text (code, configs, documentation)
INCLUDE_EXTS = {
    '.py', '.js', '.jsx', '.ts', '.tsx', '.html', '.htm', '.css', '.scss', '.sass',
    '.json', '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
    '.txt', '.md', '.rst', '.log', '.sh', '.bash', '.bat', '.cmd', '.ps1',
    '.sql', '.php', '.rb', '.go', '.rs', '.c', '.cpp', '.h', '.hpp', '.java',
    '.kt', '.swift', '.pl', '.pm', '.lua', '.r', '.dart', '.lisp', '.clj',
    '.scala', '.groovy', '.gradle', '.makefile', '.cmake', '.dockerfile',
    '.gitignore', '.gitattributes', '.editorconfig', '.env',
    '.csv', '.tsv', '.svg', '.xml', '.xslt', '.wsdl'
}

# Extension-less filenames to include as well
SPECIAL_NAMES = {
    'Dockerfile', 'Makefile', 'makefile', 'CMakeLists.txt', 'LICENSE',
    'README', 'README.md', 'CHANGELOG', 'CONTRIBUTING', 'AUTHORS'
}


def should_include_file(file_path: Path, include_exts, exclude_dirs, special_names):
    """
    Determine whether to include a file in the bundle.
    Checks:
      - not inside an excluded directory;
      - extension matches the allowed list;
      - or filename is in special names;
      - also tries to read the beginning of the file as UTF-8 (text check).
    """
    # Exclude directories
    for part in file_path.parts:
        if part in exclude_dirs:
            return False

    # Check extension or special name
    if file_path.suffix.lower() in include_exts:
        pass  # allowed by extension
    elif file_path.name in special_names:
        pass  # allowed by name
    else:
        return False  # does not qualify

    # Try reading a small chunk as UTF-8 text
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            f.read(1024)
        return True
    except (UnicodeDecodeError, PermissionError, OSError):
        return False


def collect_files(root_dir: str, include_exts=None, exclude_dirs=None, special_names=None):
    """Recursively collect all qualifying files from the root directory."""
    if include_exts is None:
        include_exts = INCLUDE_EXTS
    if exclude_dirs is None:
        exclude_dirs = EXCLUDE_DIRS
    if special_names is None:
        special_names = SPECIAL_NAMES

    root = Path(root_dir).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"'{root_dir}' is not a directory.")

    files = []
    for item in root.rglob('*'):
        if item.is_file():
            if should_include_file(item, include_exts, exclude_dirs, special_names):
                files.append(item)
    return files


def generate_output(files, output_file: str, root_dir: str):
    """Write all files to the output file with separators."""
    with open(output_file, 'w', encoding='utf-8') as out:
        out.write("=" * 80 + "\n")
        out.write("PROJECT FILES BUNDLE\n")
        out.write(f"Root directory: {root_dir}\n")
        out.write(f"Total files: {len(files)}\n")
        out.write("=" * 80 + "\n\n")

        for file_path in sorted(files):
            # Relative path from project root for clarity
            try:
                rel_path = file_path.relative_to(Path(root_dir).resolve())
            except ValueError:
                rel_path = file_path  # in case the path is not nested

            out.write(f"FILE: {rel_path}\n")
            out.write("-" * 80 + "\n")
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                out.write(content)
            except Exception as e:
                out.write(f"READ ERROR: {e}\n")
            out.write("\n" + "=" * 80 + "\n\n")


def main():
    parser = argparse.ArgumentParser(
        description="Bundle all project text files into a single file for AI input."
    )
    parser.add_argument(
        '--root', default='.',
        help='Project root directory (default: current directory)'
    )
    parser.add_argument(
        '--output', default='project_export.txt',
        help='Output file (default: project_export.txt)'
    )
    parser.add_argument(
        '--extensions', nargs='+',
        help='List of extensions to include (e.g. .py .js) — overrides the default list'
    )
    parser.add_argument(
        '--exclude-dirs', nargs='+',
        help='List of additional directories to exclude (added to defaults)'
    )
    parser.add_argument(
        '--no-default-excludes', action='store_true',
        help='Do not use the default excluded directories list'
    )
    parser.add_argument(
        '--max-size-mb', type=float, default=None,
        help='Skip files larger than the given MB (default: no limit)'
    )
    parser.add_argument(
        '--no-stats', action='store_true',
        help='Do not print stats for the output file'
    )
    args = parser.parse_args()

    root_dir = args.root
    output_file = args.output

    # Build lists
    include_exts = set(args.extensions) if args.extensions else None  # None means use default
    exclude_dirs = set(args.exclude_dirs) if args.exclude_dirs else set()
    if not args.no_default_excludes:
        exclude_dirs.update(EXCLUDE_DIRS)

    files = collect_files(root_dir, include_exts, exclude_dirs, SPECIAL_NAMES)

    # Size filter if specified
    if args.max_size_mb is not None:
        max_bytes = args.max_size_mb * 1024 * 1024
        files = [f for f in files if f.stat().st_size <= max_bytes]
        print(f"After size filter: {len(files)} files remaining.")

    print(f"Files to include: {len(files)}")
    generate_output(files, output_file, root_dir)
    print(f"Output written to {output_file}")

    # --- STATS OUTPUT ---
    if not args.no_stats:
        try:
            file_size = os.path.getsize(output_file)
            with open(output_file, 'r', encoding='utf-8') as f:
                content = f.read()
            char_count = len(content)
            approx_tokens = char_count // 4  # rough estimate

            print("\n" + "=" * 50)
            print("OUTPUT FILE STATS")
            print(f"Size on disk: {file_size} bytes "
                  f"({file_size / 1024:.2f} KB, {file_size / 1024 / 1024:.2f} MB)")
            print(f"Character count: {char_count:,}")
            print(f"Estimated tokens (chars / 4): {approx_tokens:,}")

            # Warning if typical context exceeded
            if approx_tokens > 128_000:
                print("\n⚠️  WARNING: estimated tokens exceed 128,000.")
                print("   This may not fit in the context of many modern models (GPT-4, Claude 3, etc.).")
                print("   Consider reducing the project size or splitting into parts.")
            elif approx_tokens > 16_000:
                print("\nℹ️  Estimated tokens > 16,000 — context may be largely filled.")
            else:
                print("\n✅ Estimated tokens within typical context (≤ 16,000).")
            print("=" * 50)
        except Exception as e:
            print(f"Could not compute stats: {e}")


if __name__ == '__main__':
    main()
