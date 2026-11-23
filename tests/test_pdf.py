"""보고서 PDF 변환: 그림 줄은 PDF 안에 넣고(data URI), 그림 파일이 없으면 만들지 않으며, 글자로 남는 마크다운은 알려 준다.
브라우저(Playwright)는 쓰지 않는다 — HTML 까지만."""
import base64

import pytest

from pa import pdf

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


def test_figure_line_is_embedded(tmp_path):
    (tmp_path / "그림").mkdir()
    (tmp_path / "그림" / "peak.png").write_bytes(PNG)
    h = pdf.to_html("# 보고서\n![Gapdh melt peak](그림/peak.png)\n본문", tmp_path)
    assert '<div class="fig"><img src="data:image/png;base64,' in h and 'alt="Gapdh melt peak"' in h
    assert "![" not in h.split("</style>")[1]


def test_missing_figure_stops(tmp_path):
    with pytest.raises(FileNotFoundError, match="그림 없음"):
        pdf.to_html("![x](그림/없음.png)", tmp_path)


def test_report_without_figures_unchanged(tmp_path):
    md = "# 제목\n<div align=\"right\">학번 이름</div>\n\n## 1. 결과\n- **굵게** H₂O\n\n| a | b |\n|---|---|\n| 1 | 2 |\n---\n끝"
    assert pdf.to_html(md, tmp_path) == pdf.to_html(md)
    assert "fig" not in pdf.to_html(md).split("</style>")[1]


def test_warnings_for_leftover_markdown(tmp_path):
    f = tmp_path / "r.md"
    f.write_text("# 보고서\n문장 안의 ![그림](a.png) 과 `코드` 와 *기울임* 표시\n**굵게**는 괜찮음\n", encoding="utf-8")
    names = [n for n, ex in pdf.warnings(f)]
    assert any("그림" in n for n in names) and any("코드" in n for n in names) and any("기울임" in n for n in names)
    f.write_text("# 보고서\n**굵게** 와 2 * 3 = 6 은 괜찮음\n", encoding="utf-8")
    assert pdf.warnings(f) == []
