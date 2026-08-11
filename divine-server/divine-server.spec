import os
from pathlib import Path

project_root = Path(SPECPATH)

# 目标 Mach-O 切片：darwin-arm64 / darwin-x64 时由 build-sidecar.sh 设置。
# 必须写在 spec 里（EXE 的 target_arch），不能走 CLI --target-arch —— 指定了
# .spec 文件后 makespec 选项会被 PyInstaller 拒绝。
target_arch = os.environ.get("SIDECAR_TARGET_ARCH") or None

a = Analysis(
    ["entry.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(project_root / "app" / "tools" / "scripts"), "app/tools/scripts"),
    ],
    hiddenimports=[
        "eval_type_backport",
        "docx",
        "pptx",
        "bs4",
        "openpyxl",
        "langchain_community.document_loaders",
        "langchain_community.document_loaders.text",
        "langchain_community.document_loaders.csv",
        "langchain_community.document_loaders.docx",
        "langchain_community.document_loaders.pdf",
        "langchain_community.document_loaders.excel",
        "pypdf",
        "langchain_deepseek",
        "zhipuai",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        "app.api.chat",
        "app.api.files",
        "app.api.sessions",
        "app.api.settings",
        "app.tools.adapters.describe_svg",
        "app.tools.adapters.draw_svg",
        "app.tools.adapters.edit_svg",
        "app.tools.adapters.mermaid_export",
        "app.tools.adapters.notes",
        "app.tools.adapters.presentation",
        "app.tools.adapters.svg_to_png",
        "app.tools.adapters.web_fetch",
        "app.tools.adapters.spreadsheet",
        "app.tools.adapters.terminal",
        "app.tools.adapters.ux_html",
        "app.tools.adapters.word_document",
        "app.rag_store",
        "reportlab",
        "reportlab.pdfbase",
        "reportlab.pdfbase.ttfonts",
        "reportlab.pdfbase.pdfmetrics",
        "reportlab.lib",
        "reportlab.lib.styles",
        "reportlab.lib.enums",
        "reportlab.lib.colors",
        "reportlab.lib.pagesizes",
        "reportlab.platypus",
        "resvg_py",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="divine-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    target_arch=target_arch,
)
