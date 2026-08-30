"""检索范围：科目目录（data/<科目>/*.json）的发现、来源分组与加载。"""

import json

import pytest

from mqm import (
    ALL_SUBJECTS,
    group_by_source,
    list_sources,
    list_subjects,
    load_scope,
    load_subject,
    split_scope,
    subject_files,
)


def _write(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def root(tmp_path):
    _write(tmp_path / "线性代数" / "九大.json", [
        {"id": "la-1", "school": "九州大学", "knowledge_points": ["特征值"]},
        {"id": "la-2", "school": "九州大学", "knowledge_points": ["矩阵幂"]},
    ])
    _write(tmp_path / "线性代数" / "东大.json", [
        {"id": "la-3", "school": "东京大学", "knowledge_points": ["秩"]},
    ])
    _write(tmp_path / "微积分" / "题库.json", [{"id": "ca-1", "knowledge_points": ["不定积分"]}])
    _write(tmp_path / "根目录也放了一份.json", [{"id": "root-1", "knowledge_points": ["集合"]}])
    (tmp_path / "图片" / "子目录").mkdir(parents=True)   # 没 JSON，不算科目
    return tmp_path


def test_list_subjects_skips_folders_without_questions(root):
    assert list_subjects(root) == ["微积分", "线性代数"]


def test_subject_files_only_takes_that_folder(root):
    names = [p.name for p in subject_files("线性代数", root)]
    assert names == ["东大.json", "九大.json"]


def test_load_subject_merges_every_file_in_the_folder(root):
    qids = [q.qid for q in load_subject("线性代数", None, root)]
    assert sorted(qids) == ["la-1", "la-2", "la-3"]


def test_all_subjects_covers_the_whole_data_root(root):
    qids = {q.qid for q in load_scope(ALL_SUBJECTS, None, root)}
    assert qids == {"la-1", "la-2", "la-3", "ca-1", "root-1"}


def test_unknown_subject_lists_the_available_ones(root):
    with pytest.raises(ValueError, match="线性代数"):
        load_subject("线代", None, root)


# ---------- 来源（学校 / 文件）----------

def test_sources_come_from_the_school_field(root):
    assert list_sources("线性代数", None, root) == ["东京大学", "九州大学"]


def test_source_falls_back_to_the_file_name(root):
    assert list_sources("微积分", None, root) == ["题库"]      # 没写 school


def test_group_by_source_splits_one_file_by_school(tmp_path):
    _write(tmp_path / "科目" / "合集.json", [
        {"id": "a", "school": "甲大学"}, {"id": "b", "school": "乙大学"}, {"id": "c", "school": "甲大学"},
    ])
    groups = group_by_source(subject_files("科目", tmp_path), None, tmp_path)
    assert {name: [q.qid for q in qs] for name, qs in groups.items()} == {
        "乙大学": ["b"], "甲大学": ["a", "c"],
    }


def test_load_scope_picks_one_source(root):
    qids = [q.qid for q in load_scope("线性代数/九州大学", None, root)]
    assert sorted(qids) == ["la-1", "la-2"]


def test_load_scope_rejects_unknown_source(root):
    with pytest.raises(ValueError, match="九州大学"):
        load_scope("线性代数/北海道大学", None, root)


def test_split_scope():
    assert split_scope("线性代数/九州大学") == ("线性代数", "九州大学")
    assert split_scope("线性代数") == ("线性代数", "")
    assert split_scope(ALL_SUBJECTS) == (ALL_SUBJECTS, "")


def test_colliding_default_ids_get_a_file_prefix(tmp_path):
    """两个文件都没写 id 时（各自退化成 q-0000），后来的那条加文件名前缀，不丢题。"""
    _write(tmp_path / "科目" / "a.json", [{"knowledge_points": ["A"]}])
    _write(tmp_path / "科目" / "b.json", [{"knowledge_points": ["B"]}])
    questions = load_subject("科目", None, tmp_path)
    assert [q.qid for q in questions] == ["q-0000", "科目/b:q-0000"]
    assert [q.knowledge_points for q in questions] == [["A"], ["B"]]


def test_duplicate_ids_inside_one_file_still_raise(tmp_path):
    _write(tmp_path / "科目" / "a.json", [{"id": "x"}, {"id": "x"}])
    with pytest.raises(ValueError, match="重复 id"):
        load_subject("科目", None, tmp_path)


def test_jsonl_files_are_included(tmp_path):
    (tmp_path / "科目").mkdir()
    (tmp_path / "科目" / "库.jsonl").write_text(
        '{"id": "j-1", "knowledge_points": ["行列式"]}\n', encoding="utf-8"
    )
    assert [q.qid for q in load_subject("科目", None, tmp_path)] == ["j-1"]
