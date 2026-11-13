"""자료 연결: 범위·개수 제한·짝 찾기·다운로드 목록 (Claude·네트워크 없이)."""
import os
import time
from pathlib import Path

import pytest

from pa import db, links


@pytest.fixture
def roots(tmp_path, monkeypatch):
    mat, notes = tmp_path / "materials", tmp_path / "notes"
    (mat / "organic_chemistry").mkdir(parents=True)
    notes.mkdir()
    for name in ("17강_배포용.pdf", "18강_배포용.pdf", "스크린샷 1.pdf", "a.png"):
        (mat / "organic_chemistry" / name).write_bytes(b"x")
    (notes / "17강 정리.md").write_text("노트")
    c = {"roots": [{"name": "자료", "path": mat.resolve(), "ext": {".pdf", ".md"}},
                   {"name": "노트", "path": notes.resolve(), "ext": {".md"}}],
         "skip": ["스크린샷"], "downloads": {"recent_days": 7, "ext": {".pdf"}}, "max_links": 2}
    monkeypatch.setattr(links, "cfg", lambda: c)
    links._index.update(at=0.0, files=None)
    return tmp_path


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PATH", tmp_path / "pa.db")
    return db.connect()


def test_index_skips_screenshots_and_other_types(roots):
    names = sorted(Path(x["p"]).name for x in links.index())
    assert names == ["17강 정리.md", "17강_배포용.pdf", "18강_배포용.pdf"]


def test_add_limits_scope_and_count(roots, conn):
    a = roots / "materials" / "organic_chemistry" / "17강_배포용.pdf"
    b = roots / "materials" / "organic_chemistry" / "18강_배포용.pdf"
    links.add(conn, "m1", a)
    links.add(conn, "m1", a)  # 같은 파일 다시 → 개수 안 늘어남
    links.add(conn, "m1", roots / "notes" / "17강 정리.md")
    with pytest.raises(ValueError, match="최대 2개"):
        links.add(conn, "m1", b)
    outside = roots / "elsewhere.pdf"
    outside.write_bytes(b"x")
    with pytest.raises(ValueError, match="범위 밖"):
        links.add(conn, "m2", outside)
    assert [x["name"] for x in links.get(conn, "m1")] == ["17강_배포용.pdf", "17강 정리.md"]


def test_removed_pair_is_not_added_again(roots, conn):
    a = str((roots / "materials" / "organic_chemistry" / "17강_배포용.pdf").resolve())
    assert links.save_pairs(conn, [("m1", a)]) == 1
    assert links.get(conn, "m1")[0]["origin"] == "pair"
    links.remove(conn, "m1", a)
    assert links.save_pairs(conn, [("m1", a)]) == 0  # 사용자가 뺀 짝은 다시 넣지 않음
    assert links.get(conn, "m1") == []
    links.add(conn, "m1", a)  # 직접 다시 넣으면 user 로
    assert links.get(conn, "m1")[0]["origin"] == "user"
    links.remove(conn, "m1", a)
    assert conn.execute("SELECT COUNT(*) FROM links").fetchone()[0] == 0


def test_missing_file_is_marked(roots, conn):
    f = roots / "materials" / "organic_chemistry" / "18강_배포용.pdf"
    links.add(conn, "m1", f)
    f.unlink()
    assert links.get(conn, "m1")[0]["exists"] is False
    assert links.paths(conn, "m1") == []


def test_ls_stays_inside_roots(roots):
    top = links.ls("자료")
    assert top["dirs"] == [{"name": "organic_chemistry", "count": 2}]
    inner = links.ls("자료", "organic_chemistry")
    assert [f["name"] for f in inner["files"]] == ["17강_배포용.pdf", "18강_배포용.pdf"]
    with pytest.raises(ValueError):
        links.ls("자료", "../notes")
    with pytest.raises(ValueError):
        links.ls("없는범위")


def test_recent_downloads_filter(roots):
    d = roots / "Downloads"
    d.mkdir()
    old = d / "old.pdf"
    for name in ("new.pdf", "old.pdf", "photo.png", "half.pdf.crdownload"):
        (d / name).write_bytes(b"x")
    past = time.time() - 10 * 86400
    os.utime(old, (past, past))
    links.update_recent_downloads([(f, f.stat()) for f in d.iterdir()])
    assert [Path(x["p"]).name for x in links.recent_downloads()] == ["new.pdf"]


def _item(i, title):
    return {"id": i, "type": "ExternalTool", "title": title}


def test_find_pairs_one_candidate_per_week():
    local = ["/m/17강_배포용.pdf"]
    items = [_item(1, "17강 Lecture 1) 친핵성 치환"), _item(2, "17강_배포용"), _item(3, "[출결] 17강 출석 확인")]
    assert links.find_pairs(items, local) == [("m1", "/m/17강_배포용.pdf")]


def test_find_pairs_ambiguous_week_is_not_paired():
    local = ["/m/handout A.pdf", "/m/handout B.pdf"]
    items = [_item(1, "윤리 강의"), _item(2, "handout A"), _item(3, "handout B")]
    assert links.find_pairs(items, local) == []  # 고를 수 없으면 추천으로만


def test_find_pairs_picks_by_number_when_several():
    local = ["/m/[강의자료] 9강.pdf", "/m/[강의자료] 10강.pdf"]
    items = [_item(1, "9강 강의영상"), _item(2, "10강 강의영상"),
             _item(3, "[강의자료] 9강"), _item(4, "[강의자료] 10강")]
    assert sorted(links.find_pairs(items, local)) == [("m1", "/m/[강의자료] 9강.pdf"), ("m2", "/m/[강의자료] 10강.pdf")]


def test_download_is_moved_to_course_folder_then_linked(roots, conn, monkeypatch):
    from pa import materials
    dl = roots / "Downloads"
    dl.mkdir()
    f = dl / "Ch26 handout.pdf"
    f.write_bytes(b"x")
    course_dir = roots / "materials" / "organic_chemistry"
    monkeypatch.setattr(materials, "downloads_dir", lambda: dl)
    monkeypatch.setattr(materials, "course_dirs", lambda c: (course_dir, roots / "notes") if c else None)
    links.update_recent_downloads([(f, f.stat())])
    db.sync_source(conn, "canvas", [{"key": "m9", "kind": "lecture", "course": "유기약화학Ⅱ", "title": "Ch26",
                                     "due": "2099-01-01T23:59:00+09:00", "earliest": None, "minutes": 50, "url": ""}])
    r = links.add_download(conn, "m9", str(f))
    assert r["ok"] and not f.exists() and (course_dir / "Ch26 handout.pdf").exists()
    assert [x["name"] for x in links.get(conn, "m9")] == ["Ch26 handout.pdf"]
    assert links.recent_downloads() == []  # 옮긴 파일은 바로 목록에서 빠짐
    g = dl / "x.pdf"
    g.write_bytes(b"x")
    assert links.add_download(conn, "없는키", str(g))["needCourse"]  # 과목을 모르면 옮기지 않고 묻는다
    assert g.exists()


def test_open_file_scope(tmp_path, monkeypatch):
    from pa import materials
    root, dl = tmp_path / "study", tmp_path / "Downloads"
    for d in (root, tmp_path / "study_other", dl / "sub"):
        d.mkdir(parents=True)
    ok, sibling, top, deep = root / "a.pdf", tmp_path / "study_other" / "b.pdf", dl / "c.pdf", dl / "sub" / "d.pdf"
    for x in (ok, sibling, top, deep):
        x.write_bytes(b"x")
    monkeypatch.setattr(materials, "allowed_roots", lambda: [root.resolve()])
    monkeypatch.setattr(materials, "downloads_dir", lambda: dl.resolve())
    monkeypatch.setattr(materials, "_vscode_open", lambda p: True)
    assert materials.open_file(ok) == "vscode" and materials.open_file(top) == "vscode"
    for bad in (sibling, deep):  # 이름이 비슷한 옆 폴더, 다운로드의 하위 폴더는 안 됨
        with pytest.raises(ValueError):
            materials.open_file(bad)
