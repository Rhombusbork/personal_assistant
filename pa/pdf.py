"""보고서 .md → A4 PDF (Claude 안 씀). 제출용: 쪽수를 알려 주고, 만든 뒤 탐색기에서 그 파일을 보여 준다.

마크다운은 보고서에 쓰는 만큼만 (제목, 문단, 목록, 표, 구분선, 굵게, 오른쪽 정렬 div, 아래 첨자 ₀-₉,
그림 줄 `![설명](그림/파일.png)` — .md 폴더 기준, PDF 안에 넣음. 그림 파일이 없으면 PDF 를 만들지 않는다).
변환 안 된 마크다운(`![`·`](`·`` ` ``·*기울임*)이 남으면 warnings() 가 알려 준다 (제출 전 확인에서 막음).
글꼴은 설치된 나눔고딕. 브라우저는 LearningX 로그인과 같은 Playwright Chromium.
"""
import base64
import html
import mimetypes
import os
import re
import urllib.parse
from pathlib import Path

_PW = os.path.expanduser("~/quiz_system_project/.tools/pw")  # 퀴즈 프로젝트의 브라우저를 같이 씀 (없으면 기본 위치)
if os.path.isdir(_PW):
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", _PW)

SUB = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
CSS = """@page { size: A4; margin: 13mm 15mm; }
body { font-family: 'NanumGothic','NanumSquare',sans-serif; font-size: 10.5pt; line-height: 1.45; }
h1 { font-size: 15pt; margin: 0; } h2 { font-size: 11pt; margin: 2px 0 0; font-weight: normal; color: #444; }
h3 { font-size: 10.5pt; margin: 7px 0 2px; } p { margin: 2px 0; } ul, ol { margin: 2px 0; padding-left: 16px; } li { margin: 1px 0; }
table { border-collapse: collapse; margin: 3px 0; } td, th { border: 1px solid #999; padding: 1px 8px; } th { background: #eee; }
hr { border: 0; border-top: 1px solid #bbb; margin: 8px 0; }
.fig { text-align: center; margin: 4px 0; break-inside: avoid; } .fig img { max-width: 70%; max-height: 62mm; }"""
RE_IMG = re.compile(r'^\s*!\[([^\]]*)\]\(\s*<?([^)>]+?)>?(?:\s+"[^"]*")?\s*\)\s*$')


def _inline(t):
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(t))
    return re.sub(r"[₀-₉]+", lambda m: f"<sub>{m[0].translate(SUB)}</sub>", t)


def _figure(alt, ref, base):
    """그림 줄 → data URI 로 넣은 <img> (set_content 라 경로 기준이 없고, Windows·WSL 경로 문제도 없게)."""
    path = Path(urllib.parse.unquote(ref))
    path = path if path.is_absolute() or base is None else Path(base) / path
    if not path.is_file():
        raise FileNotFoundError(f"그림 없음: {ref}")
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    data = base64.b64encode(path.read_bytes()).decode()
    return f'<div class="fig"><img src="data:{mime};base64,{data}" alt="{html.escape(alt)}"></div>'


def to_html(md, base=None):
    """base: .md 가 있는 폴더 (그림 경로의 기준)."""
    lines, out, i = md.split("\n"), [], 0
    while i < len(lines):
        line = lines[i]
        if m := RE_IMG.match(line):
            out.append(_figure(m[1], m[2], base))
        elif line.startswith("<div"):
            out.append(line)
        elif re.match(r"(-{3,}|\*{3,})\s*$", line):
            out.append("<hr>")
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
        page.set_content(to_html(src.read_text(encoding="utf-8"), src.parent))
        page.pdf(path=str(out), format="A4", prefer_css_page_size=True)
        b.close()
    return out, pages(out)


def pages(path):
    """PDF 쪽수 (라이브러리 없이 /Type /Page 개수)."""
    return len(re.findall(rb"/Type\s*/Page[^s]", Path(path).read_bytes()))


LEFTOVER = [(r"!\[", "그림 문법 ![…]"), (r"\]\(", "링크·그림 문법 ](…)"), (r"`", "코드 표시 `"),
            (r"(?<![*\w])\*(?!\s)[^*\n]+?(?<!\s)\*(?![*\w])", "기울임 *…*")]


def warnings(md_path):
    """PDF 로 바꿨을 때 글자 그대로 남는 마크다운 [(이름, 예)] — 그림 파일이 없으면 FileNotFoundError."""
    src = Path(md_path)
    body = to_html(src.read_text(encoding="utf-8"), src.parent).split("</style>", 1)[-1]
    text = html.unescape(re.sub(r"<[^>]+>", " ", body))
    out = []
    for pat, name in LEFTOVER:
        m = re.search(pat, text)
        if m:
            out.append((name, text[max(0, m.start() - 15):m.end() + 25].strip()))
    return out
