#!/usr/bin/env python3
"""
Script to run integration tests with verbose output displayed in the console.
This shows both the command details and captured output during test execution.
"""
import sys
import subprocess
import os
import argparse
import glob


def main():
    """Run integration tests with detailed output."""
    parser = argparse.ArgumentParser(
        description="Run integration tests with detailed output displayed in the console. "
        "By default, it runs all test_*_command.py files if no specific files are provided."
    )
    parser.add_argument(
        "test_files",
        nargs="*",
        default=[],
        help="Test files to run (if not specified, runs all test_*_command.py files)",
    )
    parser.add_argument(
        "-k",
        "--keyword",
        help="Only run tests with names matching this keyword expression",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all integration tests (including those not matching test_*_command.py pattern)",
    )
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))

    # If no test files specified, find all test files in the integration directory
    if not args.test_files:
        if args.all:
            # Get all test_*.py files
            test_pattern = os.path.join(script_dir, "test_*.py")
        else:
            # Get all test_*_command.py files by default
            test_pattern = os.path.join(script_dir, "test_*_command.py")

        test_files = glob.glob(test_pattern)
        # Convert to relative paths for display
        display_files = [os.path.basename(f) for f in test_files]
    else:
        # Use specified test files
        test_files = [os.path.join(script_dir, f) for f in args.test_files]
        display_files = args.test_files

    print("Running Integration Tests with Verbose Output")
    print("===========================================")
    print(f"Test files: {', '.join(display_files)}")
    if args.keyword:
        print(f"Keyword filter: {args.keyword}")
    print()

    # Build the pytest command
    cmd = ["python3", "-m", "pytest"] + test_files + ["-v", "-s"]
    if args.keyword:
        cmd.append(f"-k={args.keyword}")

    # Run the tests
    print(f"Executing: {' '.join(cmd)}\n")
    result = subprocess.run(cmd)

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
