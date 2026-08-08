from pathlib import Path

project_root = Path(SPECPATH)

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
        "app.tools.adapters.notes",
        "app.tools.adapters.presentation",
        "app.tools.adapters.web_fetch",
        "app.tools.adapters.spreadsheet",
        "app.tools.adapters.terminal",
        "app.tools.adapters.word_document",
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
    [],
    exclude_binaries=True,
    name="divine-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="divine-server",
)
