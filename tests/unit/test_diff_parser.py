from __future__ import annotations

import pytest
from proofstack_analyzers import ChangeType, DiffLineType, DiffParseError, parse_unified_diff

COMPLEX_DIFF = """diff --git a/app/service.py b/app/service.py
index 1111111..2222222 100644
--- a/app/service.py
+++ b/app/service.py
@@ -1,4 +1,5 @@ service
 def total(items):
-    return sum(items)
+    values = list(items)
+    return sum(values)
 
diff --git "a/old name.py" "b/new name.py"
similarity index 90%
rename from old name.py
rename to new name.py
--- a/old name.py
+++ b/new name.py
@@ -1 +1 @@
-OLD = True
+NEW = True
diff --git a/tests/test_service.py b/tests/test_service.py
new file mode 100644
--- /dev/null
+++ b/tests/test_service.py
@@ -0,0 +1,2 @@
+def test_total():
+    assert True
diff --git a/logo.png b/logo.png
new file mode 100644
Binary files /dev/null and b/logo.png differ
diff --git a/removed.py b/removed.py
deleted file mode 100644
--- a/removed.py
+++ /dev/null
@@ -1 +0,0 @@
-VALUE = 1
"""


def test_parse_complex_diff_and_classify_files() -> None:
    document = parse_unified_diff(COMPLEX_DIFF)

    assert len(document.files) == 5
    assert document.additions == 5
    assert document.deletions == 3
    modified, renamed, test_file, binary, removed = document.files
    assert modified.change_type is ChangeType.MODIFIED
    assert modified.changed_new_ranges == ((2, 3),)
    assert renamed.change_type is ChangeType.RENAMED
    assert renamed.old_path == "old name.py"
    assert renamed.new_path == "new name.py"
    assert test_file.change_type is ChangeType.ADDED
    assert test_file.is_test
    assert binary.is_binary
    assert removed.change_type is ChangeType.DELETED
    assert removed.new_path is None


def test_diff_lines_track_old_and_new_locations() -> None:
    document = parse_unified_diff(COMPLEX_DIFF)
    lines = document.files[0].hunks[0].lines

    removed = next(item for item in lines if item.line_type is DiffLineType.REMOVED)
    added = [item for item in lines if item.line_type is DiffLineType.ADDED]
    assert removed.old_line_number == 2
    assert removed.new_line_number is None
    assert [item.new_line_number for item in added] == [2, 3]


def test_diff_file_flags_cover_configuration_and_dependencies() -> None:
    diff = """diff --git a/pyproject.toml b/pyproject.toml
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -1 +1 @@
-version = "1"
+version = "2"
diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -1 +1 @@
-name: old
+name: new
diff --git a/alembic/versions/001.py b/alembic/versions/001.py
new file mode 100644
--- /dev/null
+++ b/alembic/versions/001.py
@@ -0,0 +1 @@
+upgrade = True
"""
    document = parse_unified_diff(diff)

    assert document.files[0].is_config
    assert document.files[0].is_dependency_manifest
    assert document.files[1].is_ci
    assert document.files[2].is_migration


def test_parse_standard_unified_diff_without_git_header() -> None:
    diff = """--- a//app/service.py
+++ b/app/service.py
@@ -1,2 +1,2 @@
-VALUE = 1
+VALUE = 2
 keep = True
--- /dev/null
+++ b/tests/test_service.py
@@ -0,0 +1 @@
+def test_value(): return VALUE == 2
"""
    document = parse_unified_diff(diff)

    assert [item.path for item in document.files] == [
        "app/service.py",
        "tests/test_service.py",
    ]
    assert document.files[0].change_type is ChangeType.MODIFIED
    assert document.files[1].change_type is ChangeType.ADDED
    assert document.additions == 2
    assert document.deletions == 1


def test_parse_git_octal_encoded_unicode_path() -> None:
    diff = 'diff --git "a/\\346\\226\\207.py" "b/\\346\\226\\207.py"\n'

    document = parse_unified_diff(diff)

    assert document.files[0].path == "\u6587.py"


@pytest.mark.parametrize(
    "text",
    [
        "diff --git a/../escape.py b/../escape.py\n",
        "diff --git a/good.py b/good.py\n@@ -1 +1 @@\n?bad\n",
        "diff --git a/good.py b/good.py\n--- a/good.py\n+++ b/good.py\n@@ invalid @@\n",
    ],
)
def test_diff_rejects_unsafe_or_malformed_content(text: str) -> None:
    with pytest.raises(DiffParseError):
        parse_unified_diff(text)
