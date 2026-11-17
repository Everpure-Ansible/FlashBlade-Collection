# Copyright: (c) 2026, Pure Storage Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for common module utilities."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from unittest.mock import Mock, patch
from plugins.module_utils.common import (
    _findstr,
    poll_until,
    remove_duplicates,
    get_error_message,
    human_to_bytes,
    human_to_real,
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


class TestPollUntil:
    """Tests for poll_until."""

    @patch("plugins.module_utils.common.time")
    def test_finished_on_first_fetch_does_not_sleep(self, mock_time):
        """A result that is already final is returned without sleeping."""
        mock_time.monotonic.return_value = 100.0
        fetch = Mock(return_value="done")

        result, timed_out = poll_until(fetch, lambda item: item == "done", 60)

        assert result == "done"
        assert timed_out is False
        fetch.assert_called_once()
        mock_time.sleep.assert_not_called()

    @patch("plugins.module_utils.common.time")
    def test_polls_until_finished(self, mock_time):
        """Fetch is repeated with a sleep between polls until finished."""
        mock_time.monotonic.side_effect = [100.0, 100.0, 110.0, 120.0]
        fetch = Mock(side_effect=["running", "running", "passed"])

        result, timed_out = poll_until(fetch, lambda item: item == "passed", 60, 10)

        assert result == "passed"
        assert timed_out is False
        assert fetch.call_count == 3
        assert mock_time.sleep.call_args_list == [((10,),), ((10,),)]

    @patch("plugins.module_utils.common.time")
    def test_timeout_returns_last_result(self, mock_time):
        """When the deadline passes the last result is returned with timed_out."""
        mock_time.monotonic.side_effect = [100.0, 100.0, 125.0]
        fetch = Mock(return_value="running")

        result, timed_out = poll_until(fetch, lambda item: item == "passed", 20, 30)

        assert result == "running"
        assert timed_out is True
        assert fetch.call_count == 2
        # the single sleep was clamped to the time left, not the interval
        mock_time.sleep.assert_called_once_with(20)

    @patch("plugins.module_utils.common.time")
    def test_none_result_is_passed_to_finished(self, mock_time):
        """A fetch returning None is handed to finished, not treated as done."""
        mock_time.monotonic.side_effect = [100.0, 100.0, 200.0]
        fetch = Mock(return_value=None)

        result, timed_out = poll_until(fetch, lambda item: item is not None, 5)

        assert result is None
        assert timed_out is True
