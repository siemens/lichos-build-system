"""
Configuration for integration tests.
"""

import pytest
import sys
import io


@pytest.fixture(autouse=True)
def capture_and_display_output(request, monkeypatch):
    """
    A fixture that captures stdout for test verification while also
    displaying the output to the console.
    This fixture is automatically applied to all tests.
    """
    # Create a string buffer to capture output
    captured = io.StringIO()
    original_stdout = sys.stdout

    class TeeOutput:
        def write(self, data):
            captured.write(data)
            original_stdout.write(data)

        def flush(self):
            captured.flush()
            original_stdout.flush()

    # Replace stdout with our Tee that captures and displays
    monkeypatch.setattr(sys, "stdout", TeeOutput())

    # Store the captured output in the test's "captured_stdout" attribute
    request.node.captured_stdout = captured

    yield
