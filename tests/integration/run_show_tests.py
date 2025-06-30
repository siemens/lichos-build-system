#!/usr/bin/env python3
"""
Script to run integration tests with verbose output displayed in the console.
This shows both the command details and captured output during test execution.
"""
import sys
import subprocess
import os
import argparse


def main():
    """Run integration tests with detailed output."""
    parser = argparse.ArgumentParser(
        description="Run integration tests with detailed output displayed in the console."
    )
    parser.add_argument(
        "test_files",
        nargs="*",
        default=[
            "test_show_command.py",
            "test_list_command.py",
            "test_log_command.py",
            "test_status_command.py",
            "test_build_command.py",
            "test_clone_command.py",
            "test_create_command.py",
            "test_trigger_command.py",
            "test_browse_command.py",
            "test_enable_command.py",
            "test_disable_command.py",
            "test_getartifacts_command.py",
            "test_workspace_command.py",
            "test_pdiff_command.py",
        ],
        help="Test files to run (default: all test_*_command.py files)",
    )
    parser.add_argument(
        "-k",
        "--keyword",
        help="Only run tests with names matching this keyword expression",
    )
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    test_files = [os.path.join(script_dir, f) for f in args.test_files]

    print("Running Integration Tests with Verbose Output")
    print("===========================================")
    print(f"Test files: {', '.join(args.test_files)}")
    if args.keyword:
        print(f"Keyword filter: {args.keyword}")
    print()

    # Build the pytest command
    cmd = ["python3", "-m", "pytest"] + test_files + ["-v", "-s"]
    if args.keyword:
        cmd.append(f"-k={args.keyword}")

    # Run the tests
    result = subprocess.run(cmd)

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
