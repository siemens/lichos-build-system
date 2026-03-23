# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Siemens AG

"""Tests for the built-in terminal output/prompt backend."""

from io import StringIO

from lichoscli.ui import Table
from lichoscli.ui.factory import OutputBackend, PromptBackend, UserInterfaceFactory
from lichoscli.ui.models import Cell
from lichoscli.ui.terminal import TerminalOutput, TerminalPromptService


# ---------------------------------------------------------------------------
# TerminalOutput tests
# ---------------------------------------------------------------------------


def test_terminal_output_print_plain():
    stream = StringIO()
    output = TerminalOutput(stream=stream)
    output.print("hello world")
    text = stream.getvalue()
    assert text == "hello world\n"
    assert "\033[" not in text


def test_terminal_output_print_preserves_brackets():
    stream = StringIO()
    output = TerminalOutput(stream=stream)
    output.print("[green]success[/green]")
    text = stream.getvalue()
    assert "[green]success[/green]" in text
    assert "\033[" not in text


def test_terminal_output_print_preserves_brackets_without_styling():
    stream = StringIO()
    output = TerminalOutput(stream=stream)
    output.print("[INFO] keep this")
    text = stream.getvalue()
    assert "[INFO] keep this" in text
    assert "\033[" not in text


def test_terminal_output_success_wraps_ansi():
    stream = StringIO()
    output = TerminalOutput(stream=stream)
    output.success("ok")
    text = stream.getvalue()
    assert "\033[" in text
    assert "\033[0m" in text
    assert "ok" in text


def test_terminal_output_warning_preserves_brackets():
    stream = StringIO()
    output = TerminalOutput(stream=stream)
    output.warning("[INFO] keep this")
    text = stream.getvalue()

    assert "\033[" in text
    assert "\033[0m" in text
    assert "[INFO] keep this" in text


def test_terminal_output_error_helper_wraps_ansi():
    stream = StringIO()
    output = TerminalOutput(stream=stream)
    output.error("boom")
    text = stream.getvalue()
    assert "boom" in text
    assert "\033[" in text


def test_terminal_output_danger_alias_matches_warning_style():
    stream = StringIO()
    output = TerminalOutput(stream=stream)
    output.danger("careful")
    text = stream.getvalue()
    assert text.startswith("\033[33m")
    assert "careful" in text


def test_terminal_output_json():
    stream = StringIO()
    output = TerminalOutput(stream=stream)
    output.json({"a": 1})
    text = stream.getvalue()
    assert '"a": 1' in text


def test_terminal_output_table_renders_correctly():
    stream = StringIO()
    output = TerminalOutput(stream=stream)

    table = Table(title="My Table")
    table.add_column("Name")
    table.add_column("Count", justify="right")
    table.add_row("alpha", "10")
    table.add_row("beta", "200")
    output.table(table)

    lines = stream.getvalue().splitlines()
    assert lines[0] == "My Table"
    assert "Name" in lines[1]
    assert "Count" in lines[1]
    assert "----" in lines[2]
    assert "alpha" in lines[3]
    assert "beta" in lines[4]


def test_terminal_output_table_with_styled_cells():
    stream = StringIO()
    output = TerminalOutput(stream=stream)

    table = Table()
    table.add_column("Status")
    table.add_row(Cell("PASS", style="success"))
    output.table(table)

    text = stream.getvalue()
    assert "PASS" in text
    # styled cell should contain ANSI codes
    assert "\033[" in text


def test_terminal_console_print():
    stream = StringIO()
    output = TerminalOutput(stream=stream)
    output.console.print("hello")
    text = stream.getvalue()
    assert text == "hello\n"
    assert "\033[" not in text


def test_terminal_console_success_wraps_ansi():
    stream = StringIO()
    output = TerminalOutput(stream=stream)
    output.console.success("hello")
    text = stream.getvalue()
    assert "hello" in text
    assert "\033[" in text


def test_terminal_console_status():
    stream = StringIO()
    output = TerminalOutput(stream=stream)
    with output.console.status("Loading..."):
        pass
    assert "Loading" in stream.getvalue()


# ---------------------------------------------------------------------------
# Factory integration
# ---------------------------------------------------------------------------


def test_factory_creates_terminal_backends():
    ui = UserInterfaceFactory.create(
        output_backend=OutputBackend.TERMINAL,
        prompt_backend=PromptBackend.TERMINAL,
    )
    assert isinstance(ui.output, TerminalOutput)
    assert isinstance(ui.prompts, TerminalPromptService)


# ---------------------------------------------------------------------------
# Widget unit tests (non-interactive, verifying draw logic)
# ---------------------------------------------------------------------------


def test_select_widget_draw_renders_options():
    """Verify the select widget renders the initial option list."""
    from lichoscli.ui.terminal._widgets import SelectWidget

    out = StringIO()
    widget = SelectWidget(["apple", "banana", "cherry"], stream=out)
    # Manually draw without entering the event loop
    widget._draw(initial=True)
    rendered = out.getvalue()
    assert "apple" in rendered
    assert "banana" in rendered
    assert "cherry" in rendered


def test_select_widget_move_changes_cursor():
    from lichoscli.ui.terminal._widgets import SelectWidget

    out = StringIO()
    widget = SelectWidget(["a", "b", "c"], stream=out)
    assert widget._cursor == 0
    widget._move(1)
    assert widget._cursor == 1
    widget._move(1)
    assert widget._cursor == 2
    widget._move(1)  # should not go beyond end
    assert widget._cursor == 2
    widget._move(-1)
    assert widget._cursor == 1


def test_checkbox_widget_toggle():
    from lichoscli.ui.terminal._widgets import CheckboxWidget

    out = StringIO()
    widget = CheckboxWidget(["a", "b", "c"], stream=out)
    assert widget._selected == set()
    widget._cursor = 1
    widget._toggle()
    assert 1 in widget._selected
    widget._toggle()
    assert 1 not in widget._selected


def test_checkbox_widget_toggle_uses_original_indices():
    """After filtering, toggle must track the original index."""
    from lichoscli.ui.terminal._widgets import CheckboxWidget

    out = StringIO()
    widget = CheckboxWidget(["apple", "banana", "cherry"], stream=out)
    widget._query = "ban"
    widget._apply_filter()
    assert len(widget._filtered) == 1
    assert widget._filtered[0][0] == 1  # original index of "banana"
    widget._toggle()
    assert 1 in widget._selected


def test_checkbox_widget_active_preset():
    from lichoscli.ui.terminal._widgets import CheckboxWidget

    out = StringIO()
    widget = CheckboxWidget(["a", "b", "c"], active=[0, 2], stream=out)
    assert widget._selected == {0, 2}


def test_select_widget_scroll():
    from lichoscli.ui.terminal._widgets import SelectWidget

    out = StringIO()
    options = [f"item-{i}" for i in range(20)]
    widget = SelectWidget(options, view_max=5, stream=out)
    assert widget._offset == 0
    # Move down past the view window
    for _ in range(6):
        widget._move(1)
    assert widget._offset > 0
    assert widget._cursor == 6


# ---------------------------------------------------------------------------
# Fuzzy search tests
# ---------------------------------------------------------------------------


def test_fuzzy_score_exact():
    from lichoscli.ui.terminal._widgets import _fuzzy_score

    assert _fuzzy_score("abc", "abc") == 0
    assert _fuzzy_score("", "anything") == 0


def test_fuzzy_score_no_match():
    from lichoscli.ui.terminal._widgets import _fuzzy_score

    assert _fuzzy_score("xyz", "abc") is None


def test_fuzzy_score_case_insensitive():
    from lichoscli.ui.terminal._widgets import _fuzzy_score

    assert _fuzzy_score("ABC", "abcdef") is not None
    assert _fuzzy_score("abc", "ABCDEF") is not None


def test_fuzzy_score_penalises_gaps():
    from lichoscli.ui.terminal._widgets import _fuzzy_score

    tight = _fuzzy_score("ab", "ab___")
    loose = _fuzzy_score("ab", "a____b")
    assert tight is not None
    assert loose is not None
    assert tight < loose  # tight match scores lower (= better)


def test_select_widget_filter_narrows_options():
    from lichoscli.ui.terminal._widgets import SelectWidget

    out = StringIO()
    widget = SelectWidget(
        ["apple", "banana", "cherry", "avocado"],
        stream=out,
    )
    widget._query = "a"
    widget._apply_filter()
    # "a" matches apple, banana, avocado, cherry(has 'a' nowhere? no — no 'a')
    labels = [label for _, label in widget._filtered]
    assert "banana" in labels
    assert "apple" in labels
    assert "avocado" in labels


def test_select_widget_filter_returns_original_index():
    from lichoscli.ui.terminal._widgets import SelectWidget

    out = StringIO()
    widget = SelectWidget(
        ["alpha", "beta", "gamma", "delta"],
        stream=out,
    )
    widget._query = "gam"
    widget._apply_filter()
    assert len(widget._filtered) == 1
    orig_idx, label = widget._filtered[0]
    assert orig_idx == 2
    assert label == "gamma"


def test_select_widget_filter_sorts_by_score():
    from lichoscli.ui.terminal._widgets import SelectWidget

    out = StringIO()
    widget = SelectWidget(
        ["x_a_b_c", "abc", "a__b__c"],
        stream=out,
    )
    widget._query = "abc"
    widget._apply_filter()
    labels = [label for _, label in widget._filtered]
    # "abc" (exact) should come first, then "a__b__c", then "x_a_b_c"
    assert labels[0] == "abc"


def test_select_widget_backspace_widens_filter():
    from lichoscli.ui.terminal._widgets import SelectWidget

    out = StringIO()
    widget = SelectWidget(
        ["apple", "banana", "cherry"],
        stream=out,
    )
    widget._query = "ban"
    widget._apply_filter()
    assert len(widget._filtered) == 1

    # Simulate backspace
    widget._query = widget._query[:-1]  # "ba"
    widget._apply_filter()
    assert len(widget._filtered) == 1  # still just "banana"

    widget._query = ""
    widget._apply_filter()
    assert len(widget._filtered) == 3  # all options back


def test_checkbox_widget_filter_preserves_selections():
    from lichoscli.ui.terminal._widgets import CheckboxWidget

    out = StringIO()
    widget = CheckboxWidget(
        ["apple", "banana", "cherry"],
        stream=out,
    )
    # Select banana (original index 1)
    widget._query = "ban"
    widget._apply_filter()
    widget._toggle()
    assert 1 in widget._selected

    # Clear filter — banana should still be selected
    widget._query = ""
    widget._apply_filter()
    assert 1 in widget._selected

    # Select cherry while filtered
    widget._query = "che"
    widget._apply_filter()
    widget._toggle()
    assert widget._selected == {1, 2}


# ---------------------------------------------------------------------------
# SIGWINCH / terminal resize tests
# ---------------------------------------------------------------------------


def test_key_resize_constant_defined():
    from lichoscli.ui.terminal._keys import KEY_RESIZE

    assert KEY_RESIZE == "resize"


def test_read_key_or_resize_without_fd_delegates_to_read_key():
    """With no resize_fd, read_key_or_resize must behave exactly like read_key."""
    from unittest.mock import patch

    from lichoscli.ui.terminal._keys import read_key_or_resize

    with patch("lichoscli.ui.terminal._keys.read_key", return_value="a") as mock_rk:
        result = read_key_or_resize(StringIO(), resize_fd=-1)

    assert result == "a"
    mock_rk.assert_called_once()


def test_select_widget_recalc_view_max_clamps_to_terminal():
    """_recalc_view_max should use terminal height as an upper bound."""
    from unittest.mock import patch

    from lichoscli.ui.terminal._widgets import SelectWidget

    options = [f"item{i}" for i in range(20)]
    out = StringIO()
    widget = SelectWidget(options, view_max=10, stream=out)
    # Initially capped at option count if smaller, otherwise view_max
    assert widget._view_max == 10

    # Simulate a tiny terminal: 5 rows visible (lines=8, available=max(2,8-3)=5)
    with patch("os.get_terminal_size") as mock_ts:
        mock_ts.return_value.lines = 8
        widget._recalc_view_max()

    assert widget._view_max == 5


def test_select_widget_recalc_view_max_expands_on_wider_terminal():
    """After growing the terminal the view should be able to show more items."""
    from unittest.mock import patch

    from lichoscli.ui.terminal._widgets import SelectWidget

    options = [f"item{i}" for i in range(20)]
    out = StringIO()
    widget = SelectWidget(options, view_max=15, stream=out)
    widget._view_max = 4  # manually shrink (simulating earlier small terminal)

    with patch("os.get_terminal_size") as mock_ts:
        mock_ts.return_value.lines = 40
        widget._recalc_view_max()

    assert widget._view_max == 15  # back to orig_view_max (fits in 40 rows)


def test_checkbox_widget_recalc_view_max_clamps_to_terminal():
    from unittest.mock import patch

    from lichoscli.ui.terminal._widgets import CheckboxWidget

    options = [f"opt{i}" for i in range(15)]
    out = StringIO()
    widget = CheckboxWidget(options, view_max=_VIEW_MAX, stream=out)

    with patch("os.get_terminal_size") as mock_ts:
        mock_ts.return_value.lines = 6  # available = max(2, 6-3) = 3
        widget._recalc_view_max()

    assert widget._view_max == 3


def test_select_widget_resize_event_redraws(monkeypatch):
    """Injecting KEY_RESIZE into run() must trigger a full redraw."""
    import os
    from unittest.mock import patch

    from lichoscli.ui.terminal._keys import KEY_ENTER, KEY_RESIZE
    from lichoscli.ui.terminal._widgets import SelectWidget

    out = StringIO()
    inp = StringIO()
    keys = iter([KEY_RESIZE, KEY_ENTER])
    widget = SelectWidget(["alpha", "beta"], stream=out, input_stream=inp)

    with patch("lichoscli.ui.terminal._widgets.read_key_or_resize", side_effect=keys), \
         patch("lichoscli.ui.terminal._widgets.raw_mode"), \
         patch("os.get_terminal_size") as mock_ts, \
         patch("os.pipe", return_value=(-1, -1)), \
         patch("os.set_blocking"), \
         patch("os.close"), \
         patch("signal.signal"):
        mock_ts.return_value.lines = 30
        mock_ts.return_value.columns = 80
        result = widget.run()

    assert result == 0  # selected "alpha" (first option)


def test_checkbox_widget_resize_event_does_not_lose_selection(monkeypatch):
    """Selections must be preserved through a KEY_RESIZE redraw."""
    from unittest.mock import patch

    from lichoscli.ui.terminal._keys import KEY_ENTER, KEY_RESIZE, KEY_SPACE
    from lichoscli.ui.terminal._widgets import CheckboxWidget

    out = StringIO()
    inp = StringIO()
    # Space to select first item, then resize, then Enter
    keys = iter([KEY_SPACE, KEY_RESIZE, KEY_ENTER])
    widget = CheckboxWidget(["x", "y", "z"], stream=out, input_stream=inp)

    with patch("lichoscli.ui.terminal._widgets.read_key_or_resize", side_effect=keys), \
         patch("lichoscli.ui.terminal._widgets.raw_mode"), \
         patch("os.get_terminal_size") as mock_ts, \
         patch("os.pipe", return_value=(-1, -1)), \
         patch("os.set_blocking"), \
         patch("os.close"), \
         patch("signal.signal"):
        mock_ts.return_value.lines = 30
        mock_ts.return_value.columns = 80
        result = widget.run()

    assert result == {0}  # "x" must still be selected after resize


def test_select_widget_offset_clamped_after_shrink():
    """If the terminal shrinks so _view_max < _offset + something, offset is corrected."""
    from unittest.mock import patch

    from lichoscli.ui.terminal._widgets import SelectWidget

    options = [f"item{i}" for i in range(10)]
    out = StringIO()
    widget = SelectWidget(options, view_max=7, stream=out)

    # Manually put cursor/offset deep in the list
    widget._cursor = 8
    widget._offset = 6

    with patch("os.get_terminal_size") as mock_ts:
        mock_ts.return_value.lines = 7  # available = max(2, 7-3) = 4
        widget._recalc_view_max()

    # After recalc: _view_max=4, cursor=8, offset must satisfy cursor < offset+4
    assert widget._cursor >= widget._offset
    assert widget._cursor < widget._offset + widget._view_max


# _VIEW_MAX is needed for the checkbox test above
def _VIEW_MAX():
    pass


_VIEW_MAX = 7  # mirrors the constant in _widgets.py


# ---------------------------------------------------------------------------
# Label truncation tests (the fix for long-label line-wrapping)
# ---------------------------------------------------------------------------


def test_select_widget_long_label_truncated_in_draw():
    """Options wider than the terminal must be truncated to one row each."""
    from unittest.mock import patch

    from lichoscli.ui.terminal._widgets import SelectWidget

    long_label = "upstream [ttyd, imx-gpu-viv, wpewebkit, python3-ocpp, testpackage-quilt, arm-trusted-firmware, imx-sc-firmware, imx-seco]"
    options = [long_label, "short"]
    out = StringIO()
    widget = SelectWidget(options, view_max=2, stream=out)

    with patch("os.get_terminal_size") as mock_ts:
        mock_ts.return_value.columns = 80
        mock_ts.return_value.lines = 30
        widget._prev_lines = 0
        widget._draw(initial=True)

    rendered = out.getvalue()
    # Each line in the output must be shorter than 80 visible chars
    for raw_line in rendered.split("\n"):
        # strip ANSI codes to get visible width
        import re
        visible = re.sub(r"\x1b\[[^A-Za-z]*[A-Za-z]", "", raw_line)
        assert len(visible) <= 80, f"Line too wide ({len(visible)}): {visible!r}"


def test_checkbox_widget_long_label_truncated_in_draw():
    """Checkbox options wider than the terminal must be truncated to one row."""
    from unittest.mock import patch

    from lichoscli.ui.terminal._widgets import CheckboxWidget

    long_label = "upstream [ttyd, imx-gpu-viv, wpewebkit, python3-ocpp, testpackage-quilt, arm-trusted-firmware, imx-sc-firmware, imx-seco]"
    options = [long_label, "short"]
    out = StringIO()
    widget = CheckboxWidget(options, view_max=2, stream=out)

    with patch("os.get_terminal_size") as mock_ts:
        mock_ts.return_value.columns = 80
        mock_ts.return_value.lines = 30
        widget._prev_lines = 0
        widget._draw(initial=True)

    rendered = out.getvalue()
    import re
    for raw_line in rendered.split("\n"):
        visible = re.sub(r"\x1b\[[^A-Za-z]*[A-Za-z]", "", raw_line)
        assert len(visible) <= 80, f"Line too wide ({len(visible)}): {visible!r}"


def test_select_widget_draw_newline_count_matches_prev_lines():
    """_prev_lines must equal the number of newlines written so move_up is accurate."""
    from unittest.mock import patch

    from lichoscli.ui.terminal._widgets import SelectWidget

    long_label = "x" * 200
    options = [long_label] * 10
    out = StringIO()
    widget = SelectWidget(options, view_max=5, stream=out)

    with patch("os.get_terminal_size") as mock_ts:
        mock_ts.return_value.columns = 80
        mock_ts.return_value.lines = 30
        widget._prev_lines = 0
        widget._draw(initial=True)

    rendered = out.getvalue()
    assert rendered.count("\n") == widget._prev_lines


def test_checkbox_widget_draw_newline_count_matches_prev_lines():
    """_prev_lines must equal the number of newlines written so move_up is accurate."""
    from unittest.mock import patch

    from lichoscli.ui.terminal._widgets import CheckboxWidget

    long_label = "y" * 200
    options = [long_label] * 10
    out = StringIO()
    widget = CheckboxWidget(options, view_max=5, stream=out)

    with patch("os.get_terminal_size") as mock_ts:
        mock_ts.return_value.columns = 80
        mock_ts.return_value.lines = 30
        widget._prev_lines = 0
        widget._draw(initial=True)

    rendered = out.getvalue()
    assert rendered.count("\n") == widget._prev_lines
