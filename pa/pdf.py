"""보고서 .md → A4 PDF (Claude 안 씀). 제출용: 쪽수를 알려 주고, 만든 뒤 탐색기에서 그 파일을 보여 준다.

마크다운은 보고서에 쓰는 만큼만 (제목, 문단, 목록, 표, 굵게, 오른쪽 정렬 div, 아래 첨자 ₀-₉).
글꼴은 설치된 나눔고딕. 브라우저는 LearningX 로그인과 같은 Playwright Chromium.
"""
import html
import os
import re
from pathlib import Path

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(Path("~/quiz_system_project/.tools/pw").expanduser()))

SUB = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
CSS = """@page { size: A4; margin: 13mm 15mm; }
body { font-family: 'NanumGothic','NanumSquare',sans-serif; font-size: 10.5pt; line-height: 1.45; }
h1 { font-size: 15pt; margin: 0; } h2 { font-size: 11pt; margin: 2px 0 0; font-weight: normal; color: #444; }
h3 { font-size: 10.5pt; margin: 7px 0 2px; } p { margin: 2px 0; } ul, ol { margin: 2px 0; padding-left: 16px; } li { margin: 1px 0; }
table { border-collapse: collapse; margin: 3px 0; } td, th { border: 1px solid #999; padding: 1px 8px; } th { background: #eee; }"""


def _inline(t):
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(t))
    return re.sub(r"[₀-₉]+", lambda m: f"<sub>{m[0].translate(SUB)}</sub>", t)


def to_html(md):
    lines, out, i = md.split("\n"), [], 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("<div"):
            out.append(line)
        elif m := re.match(r"(#{1,4}) (.*)", line):
            out.append(f"<h{len(m[1])}>{_inline(m[2])}</h{len(m[1])}>")
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                if not re.match(r"\|[-:| ]+\|\s*$", lines[i]):
                    rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            out.append("<table>" + "".join(
                "<tr>" + "".join(f"<{'th' if n == 0 else 'td'}>{_inline(c)}</{'th' if n == 0 else 'td'}>" for c in r) + "</tr>"
                for n, r in enumerate(rows)) + "</table>")
            continue
        elif re.match(r"\s*([-*]|\d+\.) ", line):
            tag = "ol" if re.match(r"\s*\d+\. ", line) else "ul"
            items = []
            while i < len(lines) and re.match(r"\s*([-*]|\d+\.) ", lines[i]):
                items.append(re.sub(r"\s*([-*]|\d+\.) ", "", lines[i], count=1))
                i += 1
            out.append(f"<{tag}>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + f"</{tag}>")
            continue
        elif line.strip():
            out.append(f"<p>{_inline(line)}</p>")
        i += 1
    return f"<!doctype html><meta charset=utf-8><style>{CSS}</style>" + "\n".join(out)


def make(md_path):
    """.md 옆에 같은 이름의 .pdf → (경로, 쪽수)."""
    from playwright.sync_api import sync_playwright
    src = Path(md_path)
    out = src.with_suffix(".pdf")
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()
        page.set_content(to_html(src.read_text()))
        page.pdf(path=str(out), format="A4", prefer_css_page_size=True)
        b.close()
    pages = len(re.findall(rb"/Type\s*/Page[^s]", out.read_bytes()))
    return out, pages
