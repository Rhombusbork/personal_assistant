"""비서 대시보드 VSCode 확장(vscode-extension/)을 .vsix 로 묶어 설치한다 — `bin/pa vscode-ext`.

확장은 VSCode 안 탭 담당: 비서 폴더 창은 처음 한 번 자동으로, 그 밖에는 탭 줄 오른쪽 위 버튼 · 상태 줄 '비서' · Ctrl+Alt+D 로
대시보드를 Simple Browser 탭으로 연다. 10초마다 엔진에 살아 있음과 창의 폴더를 알린다 (vscode-extension/extension.js).
'ui' 확장이라 VSCode 본체(WSL 이면 Windows 쪽)에 설치한다 → 로컬·WSL 어느 창에서든 동작.
node·vsce 없이 파이썬 zipfile 로 .vsix 를 만든다 (형식이 단순한 zip).
"""
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

from pa import osutil
from pa.config import ROOT

SRC = ROOT / "vscode-extension"
OUT = ROOT / "data" / "pa-dashboard.vsix"

CONTENT_TYPES = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension=".json" ContentType="application/json"/><Default Extension=".js" ContentType="application/javascript"/>
<Default Extension=".md" ContentType="text/markdown"/><Default Extension=".svg" ContentType="image/svg+xml"/><Default Extension=".vsixmanifest" ContentType="text/xml"/>
</Types>"""


def _manifest(pkg):
    from xml.sax.saxutils import escape
    return f"""<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">
  <Metadata>
    <Identity Language="en-US" Id="{pkg['name']}" Version="{pkg['version']}" Publisher="{pkg['publisher']}"/>
    <DisplayName>{escape(pkg['displayName'])}</DisplayName>
    <Description xml:space="preserve">{escape(pkg['description'])}</Description>
    <Categories>Other</Categories>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="{pkg['engines']['vscode']}"/>
      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="{','.join(pkg.get('extensionKind', ['workspace']))}"/>
    </Properties>
  </Metadata>
  <Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation>
  <Dependencies/>
  <Assets><Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/></Assets>
</PackageManifest>"""


def build():
    pkg = json.loads((SRC / "package.json").read_text(encoding="utf-8"))
    OUT.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("extension.vsixmanifest", _manifest(pkg))
        for f in sorted(SRC.iterdir()):
            if f.is_file():
                z.write(f, f"extension/{f.name}")
    return OUT, pkg


def _code_cli():
    """VSCode 본체의 명령줄 (WSL 이면 Windows 쪽 code.cmd 를 cmd.exe 로)."""
    if osutil.IS_WSL:
        return ["cmd.exe", "/c", "code"]
    if osutil.IS_WINDOWS:
        return ["cmd", "/c", "code"]
    code = shutil.which("code")
    return [code] if code else None


def install():
    vsix, pkg = build()
    cli = _code_cli()
    if not cli:
        raise RuntimeError("VSCode 명령(code)을 찾지 못했습니다 — VSCode 를 설치하고 'code' 명령을 PATH 에 넣어 주세요")
    target = osutil._win_path(vsix) if osutil.IS_WSL else str(vsix)
    r = subprocess.run(cli + ["--install-extension", target, "--force"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180, **({"cwd": "/mnt/c"} if osutil.IS_WSL else {}))
    out = (r.stdout + r.stderr).strip()
    if r.returncode != 0:
        raise RuntimeError(out.splitlines()[-1] if out else "설치 실패")
    return f"{pkg['publisher']}.{pkg['name']} {pkg['version']}", out
