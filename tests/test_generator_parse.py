import pytest

from nl2sql.generator import _parse


@pytest.mark.parametrize("text", [
    "```sql\nselect 1\n```",
    "```SQL\nselect 1\n```",
    "```duckdb\nselect 1\n```",
    "```sqlite\nselect 1\n```",
    "```\nselect 1\n```",
    "Here is the query:\n```sql\nselect 1\n```\nIt returns one row.",
    "```sql\r\nselect 1\r\n```",
])
def test_sql_block_with_any_language_tag(text):
    assert _parse(text) == ("select 1", None)


def test_first_block_wins():
    assert _parse("```sql\nselect 1\n```\nor\n```sql\nselect 2\n```") == ("select 1", None)


def test_refusal_is_read():
    assert _parse("CANNOT_ANSWER: no profit data.") == (None, "no profit data.")
    assert _parse("I checked.\nCANNOT_ANSWER: no profit data.") == (None, "no profit data.")


def test_comment_mentioning_refusal_is_not_a_refusal():
    sql, cannot = _parse("```sql\n-- CANNOT_ANSWER: handled below\nselect 1\n```")
    assert cannot is None and sql.endswith("select 1")


@pytest.mark.parametrize("text", ["", "I am not sure what you mean.", "```sql\nselect 1"])
def test_nothing_usable_returns_none(text):
    assert _parse(text) == (None, None)