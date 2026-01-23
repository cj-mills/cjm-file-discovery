#!/usr/bin/env python3
"""
CLI Demo for cjm-file-discovery library.

This demo showcases:
1. FileScanner - High-level scanning with caching
2. LocalDiscoveryProvider - Local file system discovery
3. ScanConfig/FilterConfig - Configurable filtering
4. FileInfo/FileType - Rich file metadata

Usage:
    python demo_app.py [directory] [options]

Examples:
    python demo_app.py                          # Scan current directory
    python demo_app.py ~/Documents              # Scan specific directory
    python demo_app.py ~/Music --type audio     # Scan for audio files only
    python demo_app.py . --ext py js ts         # Scan for code files
    python demo_app.py . --depth 2              # Limit recursion depth
    python demo_app.py . --summary              # Show summary statistics
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from cjm_file_discovery.core.models import FileInfo, FileType
from cjm_file_discovery.core.config import ScanConfig, FilterConfig, ExtensionMapping
from cjm_file_discovery.scanning.scanner import FileScanner
from cjm_file_discovery.providers.local import LocalDiscoveryProvider


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Scan directories for files with configurable filtering.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              Scan current directory
  %(prog)s ~/Documents                  Scan specific directory
  %(prog)s ~/Music --type audio         Scan for audio files only
  %(prog)s . --ext py js ts             Scan for specific extensions
  %(prog)s . --depth 2                  Limit recursion depth
  %(prog)s . --summary                  Show summary statistics only
  %(prog)s . --min-size 1MB             Filter by minimum size
  %(prog)s . --max-size 100KB           Filter by maximum size
        """
    )

    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to scan (default: current directory)"
    )

    parser.add_argument(
        "--ext", "-e",
        nargs="+",
        metavar="EXT",
        help="Filter by file extensions (e.g., --ext py js ts)"
    )

    parser.add_argument(
        "--type", "-t",
        nargs="+",
        choices=["audio", "video", "image", "document", "code", "data", "archive", "other"],
        metavar="TYPE",
        help="Filter by file type (audio, video, image, document, code, data, archive, other)"
    )

    parser.add_argument(
        "--depth", "-d",
        type=int,
        metavar="N",
        help="Maximum recursion depth"
    )

    parser.add_argument(
        "--no-recursive", "-nr",
        action="store_true",
        help="Don't scan subdirectories"
    )

    parser.add_argument(
        "--hidden", "-H",
        action="store_true",
        help="Include hidden files and directories"
    )

    parser.add_argument(
        "--follow-symlinks", "-L",
        action="store_true",
        help="Follow symbolic links"
    )

    parser.add_argument(
        "--min-size",
        metavar="SIZE",
        help="Minimum file size (e.g., 1KB, 5MB, 1GB)"
    )

    parser.add_argument(
        "--max-size",
        metavar="SIZE",
        help="Maximum file size (e.g., 100KB, 10MB)"
    )

    parser.add_argument(
        "--limit", "-n",
        type=int,
        metavar="N",
        help="Maximum number of results"
    )

    parser.add_argument(
        "--sort", "-s",
        choices=["name", "size", "modified", "type"],
        default="name",
        help="Sort results by (default: name)"
    )

    parser.add_argument(
        "--desc",
        action="store_true",
        help="Sort in descending order"
    )

    parser.add_argument(
        "--summary",
        action="store_true",
        help="Show summary statistics only"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed file information"
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    return parser.parse_args()


def parse_size(size_str: str) -> int:
    """Parse a human-readable size string to bytes."""
    size_str = size_str.strip().upper()

    multipliers = {
        'B': 1,
        'KB': 1024,
        'MB': 1024 * 1024,
        'GB': 1024 * 1024 * 1024,
        'TB': 1024 * 1024 * 1024 * 1024,
    }

    for suffix, multiplier in multipliers.items():
        if size_str.endswith(suffix):
            try:
                value = float(size_str[:-len(suffix)])
                return int(value * multiplier)
            except ValueError:
                pass

    # Try parsing as raw bytes
    try:
        return int(size_str)
    except ValueError:
        raise ValueError(f"Invalid size format: {size_str}")


def format_file_row(file: FileInfo, verbose: bool = False) -> str:
    """Format a file entry for display."""
    type_badge = f"[{file.file_type.value:8}]"
    size_str = file.size_str.rjust(10) if file.size_str else "".rjust(10)

    if verbose:
        modified = file.modified_str if file.modified_str else "Unknown"
        return f"{type_badge} {size_str}  {modified:15}  {file.path}"
    else:
        return f"{type_badge} {size_str}  {file.name}"


def print_summary(summary: dict) -> None:
    """Print scan summary statistics."""
    print("\n" + "=" * 60)
    print("SCAN SUMMARY")
    print("=" * 60)

    print(f"\nTotal Files: {summary['total_files']}")
    print(f"Total Size:  {summary['total_size_str']}")

    if summary['by_type']:
        print("\nBy Type:")
        for file_type, count in sorted(summary['by_type'].items(), key=lambda x: x[1], reverse=True):
            print(f"  {file_type:10} : {count:5} files")

    if summary['by_extension']:
        print("\nTop Extensions:")
        for ext, count in summary['by_extension'].items():
            print(f"  .{ext:9} : {count:5} files")

    print("\nDirectories Scanned:")
    for directory in summary['directories']:
        print(f"  {directory}")

    print("=" * 60)


def output_json(files: List[FileInfo], summary: dict) -> None:
    """Output results as JSON."""
    import json

    result = {
        "summary": {
            "total_files": summary['total_files'],
            "total_size": summary['total_size'],
            "total_size_str": summary['total_size_str'],
            "by_type": summary['by_type'],
            "by_extension": summary['by_extension'],
        },
        "files": [
            {
                "name": f.name,
                "path": f.path,
                "size": f.size,
                "size_str": f.size_str,
                "type": f.file_type.value,
                "extension": f.extension,
                "modified": f.modified,
                "modified_str": f.modified_str,
                "mime_type": f.mime_type,
            }
            for f in files
        ]
    }

    print(json.dumps(result, indent=2))


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Validate directory
    directory = Path(args.directory).resolve()
    if not directory.exists():
        print(f"Error: Directory does not exist: {directory}", file=sys.stderr)
        return 1
    if not directory.is_dir():
        print(f"Error: Not a directory: {directory}", file=sys.stderr)
        return 1

    # Build filter config
    filter_config = FilterConfig(
        extensions=args.ext,
        file_types=[FileType(t) for t in args.type] if args.type else None,
        include_hidden=args.hidden,
    )

    # Parse size filters
    if args.min_size:
        try:
            filter_config.min_size = parse_size(args.min_size)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    if args.max_size:
        try:
            filter_config.max_size = parse_size(args.max_size)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    # Build scan config
    scan_config = ScanConfig(
        directories=[str(directory)],
        recursive=not args.no_recursive,
        max_depth=args.depth,
        follow_symlinks=args.follow_symlinks,
        filter_config=filter_config,
        max_results=args.limit,
        sort_by=args.sort,
        sort_descending=args.desc,
        cache_results=False,  # No caching for CLI
    )

    # Create scanner and scan
    scanner = FileScanner(scan_config)

    if not args.json:
        print(f"\nScanning: {directory}")
        if args.ext:
            print(f"Extensions: {', '.join(args.ext)}")
        if args.type:
            print(f"Types: {', '.join(args.type)}")
        print()

    try:
        files = scanner.scan()
    except Exception as e:
        print(f"Error during scan: {e}", file=sys.stderr)
        return 1

    # Get summary
    summary = scanner.get_summary()

    # Output results
    if args.json:
        output_json(files, summary)
    elif args.summary:
        print_summary(summary)
    else:
        # Print file list
        if files:
            if args.verbose:
                print(f"{'Type':10} {'Size':>10}  {'Modified':15}  Path")
                print("-" * 80)

            for file in files:
                print(format_file_row(file, args.verbose))

            print(f"\n{len(files)} file(s) found, {summary['total_size_str']} total")
        else:
            print("No files found matching the criteria.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
