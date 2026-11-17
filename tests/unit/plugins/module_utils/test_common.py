# Copyright: (c) 2026, Pure Storage Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for common module utilities."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from unittest.mock import Mock, patch
from plugins.module_utils.common import (
    _findstr,
    remove_duplicates,
    get_error_message,
    human_to_bytes,
    human_to_real,
    wait_for,
)


class TestFindstr:
    """Tests for _findstr function."""

    def test_match_found_single_line(self):
        """Test finding match in single line."""
        text = "this is a test line"
        assert _findstr(text, "test") == "this is a test line"

    def test_match_found_multiline(self):
        """Test finding match in multiline text."""
        text = "line1\nline2 target\nline3"
        assert _findstr(text, "target") == "line2 target"

    def test_match_found_first_occurrence(self):
        """Test that first occurrence is returned."""
        text = "line1 match\nline2 match\nline3"
        assert _findstr(text, "match") == "line1 match"

    def test_match_not_found(self):
        """Test that None is returned when match not found."""
        text = "line1\nline2\nline3"
        assert _findstr(text, "missing") is None

    def test_empty_text(self):
        """Test with empty text."""
        assert _findstr("", "test") is None

    def test_empty_match(self):
        """Test with empty match string."""
        text = "line1\nline2"
        # Empty string matches every line, should return first line
        assert _findstr(text, "") == "line1"

    def test_partial_match(self):
        """Test partial string matching."""
        text = "prefix_target_suffix"
        assert _findstr(text, "target") == "prefix_target_suffix"

    def test_case_sensitive(self):
        """Test that matching is case-sensitive."""
        text = "line1 TEST\nline2 test"
        assert _findstr(text, "test") == "line2 test"
        assert _findstr(text, "TEST") == "line1 TEST"


class TestRemoveDuplicates:
    """Tests for remove_duplicates function."""

    def test_no_duplicates(self):
        """Test list with no duplicates."""
        assert remove_duplicates([1, 2, 3, 4]) == [1, 2, 3, 4]

    def test_with_duplicates(self):
        """Test list with duplicates."""
        assert remove_duplicates([1, 2, 2, 3, 1]) == [1, 2, 3]

    def test_preserves_order(self):
        """Test that original order is preserved."""
        assert remove_duplicates([3, 1, 2, 1, 3]) == [3, 1, 2]

    def test_empty_list(self):
        """Test empty list."""
        assert remove_duplicates([]) == []

    def test_all_duplicates(self):
        """Test list where all elements are the same."""
        assert remove_duplicates([1, 1, 1, 1]) == [1]

    def test_strings(self):
        """Test with string elements."""
        assert remove_duplicates(["a", "b", "a", "c"]) == ["a", "b", "c"]

    def test_mixed_types(self):
        """Test with mixed types."""
        assert remove_duplicates([1, "1", 1, "1"]) == [1, "1"]


class TestGetErrorMessage:
    """Tests for get_error_message function."""

    def test_with_error_message(self):
        """Test extracting error message from response."""
        response = Mock()
        error = Mock()
        error.message = "Test error message"
        response.errors = [error]
        assert get_error_message(response) == "Test error message"

    def test_with_multiple_errors(self):
        """Test that first error is returned when multiple exist."""
        response = Mock()
        error1 = Mock()
        error1.message = "First error"
        error2 = Mock()
        error2.message = "Second error"
        response.errors = [error1, error2]
        assert get_error_message(response) == "First error"

    def test_with_empty_errors_list(self):
        """Test with empty errors list."""
        response = Mock()
        response.errors = []
        assert get_error_message(response) == "Unknown error"

    def test_with_no_errors_attribute(self):
        """Test with response that has no errors attribute."""
        response = Mock(spec=[])
        assert get_error_message(response) == "Unknown error"

    def test_with_custom_default(self):
        """Test with custom default message."""
        response = Mock()
        response.errors = []
        assert get_error_message(response, "Custom default") == "Custom default"

    def test_with_none_errors(self):
        """Test with None errors attribute."""
        response = Mock()
        response.errors = None
        assert get_error_message(response) == "Unknown error"


class TestHumanToBytes:
    """Tests for human_to_bytes function."""

    def test_bytes(self):
        """Test byte conversion."""
        assert human_to_bytes("100B") == 100
        assert human_to_bytes("1024B") == 1024

    def test_kilobytes(self):
        """Test kilobyte conversion."""
        assert human_to_bytes("1K") == 1024
        assert human_to_bytes("10K") == 10240

    def test_megabytes(self):
        """Test megabyte conversion."""
        assert human_to_bytes("1M") == 1048576
        assert human_to_bytes("100M") == 104857600

    def test_gigabytes(self):
        """Test gigabyte conversion."""
        assert human_to_bytes("1G") == 1073741824
        assert human_to_bytes("100G") == 107374182400

    def test_terabytes(self):
        """Test terabyte conversion."""
        assert human_to_bytes("1T") == 1099511627776
        assert human_to_bytes("10T") == 10995116277760

    def test_petabytes(self):
        """Test petabyte conversion."""
        assert human_to_bytes("1P") == 1125899906842624

    def test_case_insensitive(self):
        """Test that units are case-insensitive."""
        assert human_to_bytes("1g") == 1073741824
        assert human_to_bytes("1G") == 1073741824


class TestHumanToReal:
    """Tests for human_to_real function."""

    def test_plain_number(self):
        """Test plain number without suffix."""
        assert human_to_real("1000") == "1000"
        assert human_to_real("5000") == "5000"

    def test_thousands(self):
        """Test K (thousands) suffix."""
        assert human_to_real("1K") == 1000
        assert human_to_real("10K") == 10000
        assert human_to_real("100K") == 100000

    def test_millions(self):
        """Test M (millions) suffix."""
        assert human_to_real("1M") == 1000000
        assert human_to_real("10M") == 10000000

    def test_case_insensitive(self):
        """Test that units are case-insensitive."""
        assert human_to_real("5k") == 5000
        assert human_to_real("5K") == 5000
        assert human_to_real("2m") == 2000000
        assert human_to_real("2M") == 2000000


class TestWaitFor:
    """Tests for the wait_for polling helper."""

    @staticmethod
    def _module(check_mode=False):
        module = Mock()
        module.check_mode = check_mode
        module.fail_json = Mock(side_effect=SystemExit)
        return module

    @patch("plugins.module_utils.common.time")
    def test_returns_when_done_on_first_probe(self, mock_time):
        mock_time.monotonic.return_value = 0
        module = self._module()
        result = wait_for(module, lambda: "done", lambda v: v == "done", 60, "x")
        assert result == "done"
        mock_time.sleep.assert_not_called()
        module.fail_json.assert_not_called()

    @patch("plugins.module_utils.common.time")
    def test_polls_with_backoff_until_done(self, mock_time):
        mock_time.monotonic.side_effect = [0, 1, 2]
        module = self._module()
        probe = Mock(side_effect=["queued", "running", "completed"])
        result = wait_for(
            module, probe, lambda v: v == "completed", 600, "run 3 to complete"
        )
        assert result == "completed"
        assert probe.call_count == 3
        # 5 s then 7.5 s: interval backs off by half each time
        assert [c[0][0] for c in mock_time.sleep.call_args_list] == [5, 7.5]

    @patch("plugins.module_utils.common.time")
    def test_sleep_never_overshoots_deadline(self, mock_time):
        mock_time.monotonic.side_effect = [0, 58, 70]
        module = self._module()
        probe = Mock(side_effect=["running", "completed"])
        wait_for(module, probe, lambda v: v == "completed", 60, "x")
        assert mock_time.sleep.call_args_list[0][0][0] == 2

    @patch("plugins.module_utils.common.time")
    def test_fails_on_terminal_failure(self, mock_time):
        mock_time.monotonic.return_value = 0
        module = self._module()
        try:
            wait_for(
                module,
                lambda: "failed",
                lambda v: v == "completed",
                60,
                "run 3 to complete",
                is_failed=lambda v: "status failed" if v == "failed" else None,
            )
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert msg == "Failed while waiting for run 3 to complete. Error: status failed"
        mock_time.sleep.assert_not_called()

    @patch("plugins.module_utils.common.time")
    def test_times_out_with_detail(self, mock_time):
        mock_time.monotonic.side_effect = [0, 100]
        module = self._module()
        try:
            wait_for(
                module,
                lambda: "running",
                lambda v: v == "completed",
                50,
                "run 3 to complete",
                detail="status {0}".format,
            )
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert msg == (
            "Timed out after 50 seconds waiting for run 3 to complete. "
            "Last reported: status running"
        )
        mock_time.sleep.assert_not_called()

    @patch("plugins.module_utils.common.time")
    def test_times_out_without_detail(self, mock_time):
        mock_time.monotonic.side_effect = [0, 100]
        module = self._module()
        try:
            wait_for(module, lambda: None, lambda v: v is not None, 50, "x")
        except SystemExit:
            pass
        assert module.fail_json.call_args[1]["msg"] == (
            "Timed out after 50 seconds waiting for x."
        )

    @patch("plugins.module_utils.common.time")
    def test_skipped_in_check_mode(self, mock_time):
        module = self._module(check_mode=True)
        probe = Mock()
        assert wait_for(module, probe, lambda v: True, 60, "x") is None
        probe.assert_not_called()
        mock_time.monotonic.assert_not_called()

    @patch("plugins.module_utils.common.time")
    def test_polls_in_check_mode_when_asked(self, mock_time):
        mock_time.monotonic.return_value = 0
        module = self._module(check_mode=True)
        probe = Mock(return_value="done")
        result = wait_for(
            module, probe, lambda v: True, 60, "x", skip_in_check_mode=False
        )
        assert result == "done"
        probe.assert_called_once()
