# Integration Tests for LichosCLI

This directory contains integration tests for LichosCLI commands that print output to the console.

## Overview

These tests verify that the various commands in LichosCLI that display information to users function correctly. 
They use mocking to isolate the commands from external dependencies and test their output formatting and behavior.

## Test Files

- `test_list_command_new.py`: Tests the `list` command that displays all packages
- `test_status_command.py`: Tests the `status` command that shows build status of packages
- `test_show_command.py`: Tests the `show` command that displays detailed package information
- `test_log_command.py`: Tests the `log` command that displays CI job logs

## Running the Tests

You can run all integration tests using the provided script:

```bash
./run_integration_tests.py
```

Or run individual test files with pytest:

```bash
pytest -v tests/integration/test_list_command_new.py
pytest -v tests/integration/test_status_command.py
pytest -v tests/integration/test_show_command.py
pytest -v tests/integration/test_log_command.py
```

### Viewing Command Output During Testing

To see the actual command output during test execution, use the `run_tests_with_output.py` script:

```bash
# Run all show command tests with output visible
./tests/integration/run_tests_with_output.py

# Run specific test file(s)
./tests/integration/run_tests_with_output.py test_list_command.py test_status_command.py

# Run tests matching a keyword
./tests/integration/run_tests_with_output.py -k "branches"
```

This will display:
1. The command being executed and its arguments
2. The captured output from each command
3. The test assertion results

This is particularly useful for debugging and understanding what each command produces.

## Test Approach

These tests focus on:

1. **Output formatting** - Ensuring that commands produce properly formatted output with all expected elements
2. **Error handling** - Verifying that commands handle errors gracefully (e.g., non-existent packages)
3. **Command behavior** - Testing that each command does what it's supposed to do

The tests use mocking to simulate external dependencies like:
- GitLab API responses
- Package and pipeline data
- Terminal output

## Adding More Tests

When adding new commands or modifying existing ones that print output, the corresponding integration tests should be updated or created. The integration tests should verify that:

1. The command produces the expected output format
2. All required data is included in the output
3. The command handles edge cases properly (empty data, errors, etc.)
