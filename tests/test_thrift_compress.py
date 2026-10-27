from thrift_compress import compress, compress_digest, fidelity


def test_fidelity_protected_spans_and_code_fence():
    source = (
        "# Digest\n"
        "Path /Users/example/project/server.py, ticket TK-000000000000, "
        "sha f117e2315752e3cbc61b4f376891d7ced5952d2bb69c7a6303b36af1a3e703eb.\n"
        "```python\nvalue = 'the the a an'\n```\n"
    )
    result = compress(source, budget="medium")
    assert "/Users/example/project/server.py" in result
    assert "TK-000000000000" in result
    assert "f117e2315752e3cbc61b4f376891d7ced5952d2bb69c7a6303b36af1a3e703eb" in result
    assert "value = 'the the a an'" in result
    assert fidelity(source, result) == 1.0


def test_compression_changes_filler_but_keeps_heading():
    source = "# Digest title\nPlease make sure to utilize the database in order to log.\n"
    result = compress(source, budget="medium")
    assert result.startswith("# Digest title\n")
    assert "utilize" not in result
    assert "database" not in result
    assert "DB" in result


def test_digest_titles_are_verbatim():
    source = "## Progress\n- **Please utilize the database** (`codex`): Please make sure to utilize the database.\n"
    result = compress_digest(source)
    assert "**Please utilize the database**" in result
    assert result.count("utilize") == 1
    assert "DB" in result


def test_plain_entry_title_is_verbatim():
    source = "- Refactored the database configuration in the deployment environment (`codex-sub`)"
    result = compress_digest(source)
    assert result == source + "\n"


def test_single_hash_heading_is_verbatim():
    source = "# The database configuration for repository auth"
    assert compress_digest(source) == source + "\n"
