"""样张主题（keynote / devconf）专属渲染器测试。

隔离边界：这两套主题带 "sample" 标记，add_slide 入口整页委托
sample_pages.render_slide，通用版式不参与——其它主题渲染路径必须零污染。
"""

import json
import subprocess
import sys
from pathlib import Path

from pptx import Presentation

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SCRIPT = Path(__file__).resolve().parents[1] / "app" / "tools" / "scripts" / "presentation.py"


def _run(payload: dict, tmp_path: Path) -> dict:
    body = {
        "workspace": str(tmp_path / "workspace"),
        "output_dir": str(tmp_path / "output"),
        "params": payload,
    }
    (tmp_path / "workspace").mkdir(parents=True, exist_ok=True)
    (tmp_path / "output").mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(body, ensure_ascii=False),
        capture_output=True, text=True, timeout=90, check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    return json.loads(completed.stdout)


_FULL_DECK = [
    {"layout": "cover", "heading": "AI Divine", "subtitle": "桌面 AI 助手",
     "brand": "AI Divine", "event": "DEVCONF 2026", "kicker": "Product Keynote",
     "date": "2026.09.28", "place": "线上直播"},
    {"layout": "bullets", "heading": "三个断点", "kicker": "The Gap",
     "points": ["文件无法直接读写|上传再下载", "产物与工作区脱节|手动搬运"]},
    {"layout": "section", "heading": "应被跳过的章节页"},
    {"layout": "toc", "heading": "目录", "points": ["A|P03"]},
    {"layout": "timeline", "heading": "发展历程", "kicker": "Milestones",
     "points": ["2024|立项", "2026|3.0"]},
    {"layout": "kpi", "heading": "用数字认识我们", "kicker": "Numbers",
     "points": ["120万+|注册用户|+38%", "4.9|商店评分"]},
    {"layout": "cards", "heading": "六大亮点", "kicker": "Highlights",
     "points": ["零代码编排|可视化搭建", "混合检索|毫秒召回",
                "实时报表|随开随用", "多端同步|全平台",
                "开放 API|深度集成", "企业级安全|私有化"]},
    {"layout": "two_col", "heading": "深潜页", "kicker": "Feature 01",
     "subtitle": "两句话说明。", "points": ["拖拽|上手快"]},
    {"layout": "columns", "heading": "三种姿势", "kicker": "Use Cases",
     "points": ["个人效率|一肩挑", "团队协作|模板库", "开发者|API"]},
    {"layout": "compare", "heading": "为什么选择我们", "kicker": "Why Us",
     "left": {"title": "AI Divine", "points": ["本地优先|不出本机"]},
     "right": {"title": "云端助手", "points": ["上传下载|链路长"]}},
    {"layout": "quote", "heading": "好的工具像空气一样安静", "kicker": "Manifesto",
     "subtitle": "AI Divine 团队"},
    {"layout": "table", "heading": "竞品对比", "kicker": "Compare",
     "table": {"columns": ["能力", "我们"], "rows": [["文件读写", "本地直读"]]}},
    {"layout": "chart", "heading": "增长曲线", "kicker": "Growth",
     "chart": {"type": "column", "categories": ["Q1", "Q2"],
               "series": [{"name": "营收", "values": [312, 444]}]}},
    {"layout": "end", "heading": "现在就开始创造", "subtitle": "divine.dev",
     "brand": "AI Divine", "points": ["立即体验", "View Docs"]},
]


def test_sample_themes_skip_section_and_toc(tmp_path):
    """devconf：固定 12 页配方装配（槽位匹配 + 缺失补占位页，006 pop 同款）；
    keynote：首个 section 保留为使命宣言页，多余 section/toc 跳过。"""
    for theme in ("devconf", "keynote"):
        result = _run({"title": "样张主题", "theme": theme, "toc": True,
                       "slides": _FULL_DECK}, tmp_path)
        assert result["success"] is True, result
        data = result["data"]
        assert any("目录页" in w for w in data["warnings"]), theme
        prs = Presentation(result["filepath"])
        all_txt = "\n".join(sh.text_frame.text for s in prs.slides
                            for sh in s.shapes if sh.has_text_frame)
        if theme == "devconf":
            # 配方装配：≥12 页核心结构；缺失槽位有占位页提示；核心槽位在页序中
            assert data["slides"] >= 12, theme
            assert any("占位页" in w for w in data["warnings"]), theme
            for token in ("用数字认识我们", "六大亮点", "增长的背后是留存",
                          "竞品对比", "BRAND MANIFESTO"):
                assert token in all_txt, (theme, token)
            # 大纲里的 section 被配方收编为使命宣言页
            assert "应被跳过的章节页" in all_txt, theme
        else:
            # keynote：同样配方装配（8 页核心 + 追加内容），缺失槽位有占位提示
            assert data["slides"] >= 8, theme
            assert any("占位页" in w for w in data["warnings"]), theme
            assert "应被跳过的章节页" in all_txt, theme
            for token in ("六大亮点", "用数字认识我们", "现在就开始创造"):
                assert token in all_txt, (theme, token)


def test_devconf_sample_pages_fidelity(tmp_path):
    """devconf 关键构图元素：fcard 眉题 / 数据带 / 宣言页 kicker / 白底表头。"""
    result = _run({"title": "AI Divine 产品宣讲", "theme": "devconf",
                   "slides": _FULL_DECK}, tmp_path)
    assert result["success"] is True, result
    prs = Presentation(result["filepath"])

    def texts(slide):
        return "\n".join(sh.text_frame.text for sh in slide.shapes
                         if sh.has_text_frame)

    all_texts = [texts(s) for s in prs.slides]
    joined = "\n".join(all_texts)
    # 封面：品牌行 + 大会名 + 眉题（016 P1）
    assert "AI DIVINE" in all_texts[0]
    assert "DEVCONF 2026" in all_texts[0]
    # 章节页/目录页已跳过，无大数字分隔页文案泄漏
    for t in all_texts:
        assert "PART" not in t
    # fcard 网格（016 P5）：FEATURE NN 眉题
    assert "FEATURE 01" in joined and "FEATURE 06" in joined
    # 数据带（016 P3）：数值 + delta 胶囊
    assert "120" in joined and "+38%" in joined
    # 表格：compare 条目已转为 016 式对比表（mono 大写表头，3 列）
    tables = [sh.table for slide in prs.slides for sh in slide.shapes
              if sh.has_table]
    assert tables
    header = [tables[0].cell(0, c).text
              for c in range(len(tables[0].columns))]
    # 表头内容完整；本品列（第 2 列）表头蓝底反白（016 .vs th.us）
    assert header == ["能力维度", "AI DIVINE", "云端助手"]
    from pptx.dml.color import RGBColor
    us_header = tables[0].cell(0, 1)
    assert us_header.fill.fore_color.rgb == RGBColor(0x2F, 0x7B, 0xF7)
    # 本品行浅灰底（016 td.us ≈ #F4F5F6 系）
    assert tables[0].cell(1, 1).fill.fore_color.rgb != RGBColor(0xFF, 0xFF, 0xFF)
    # 首数据行：能力 + ✓ 我方 + ✕ 对方（016 P10 语义）
    assert tables[0].cell(1, 1).text.startswith("✓")
    assert tables[0].cell(1, 2).text.startswith("✕")
    assert str(tables[0].cell(0, 0).fill.fore_color.rgb) == "FFFFFF"


def test_keynote_sample_pages_fidelity(tmp_path):
    """keynote 关键构图元素：蓝点眉题 / 图标块 / 进度点页脚 / 编号行。"""
    result = _run({"title": "AI Divine 产品宣讲", "theme": "keynote",
                   "slides": _FULL_DECK}, tmp_path)
    assert result["success"] is True, result
    prs = Presentation(result["filepath"])

    def texts(slide):
        return "\n".join(sh.text_frame.text for sh in slide.shapes
                         if sh.has_text_frame)

    assert "AI Divine" in texts(prs.slides[0])  # 品牌行（原样大小写）
    # 固定配方装配：P2 = 愿景宣言占位页（Part 01 签名），缺失槽位有占位提示
    data = result["data"]
    assert data["slides"] >= 8, data
    assert any("占位页" in w for w in data["warnings"]), data
    assert "Part 01" in texts(prs.slides[1])
    # 核心槽位在页序中：特性三卡 / 数据带 / 对比 / 价格收尾
    joined = "\n".join(texts(s) for s in prs.slides)
    for token in ("六大亮点", "用数字认识我们", "现在就开始创造"):
        assert token in joined, token


def test_theme_colors_override_sample_themes(tmp_path):
    """theme_colors 主色覆盖对所有主题生效（含样张主题），亮度自动校正。"""
    from app.docgen.ppt.renderer.themes import (
        apply_primary_color, get_ppt_theme,
    )

    for theme in ("devconf", "keynote"):
        expected = apply_primary_color(
            dict(get_ppt_theme(theme)), "红色")["accent"]
        result = _run({"title": "换色验证", "theme": theme,
                       "theme_colors": {"--color-primary": "红色"},
                       "slides": [{"layout": "cover", "heading": "T",
                                   "brand": "BRAND"}]}, tmp_path)
        assert result["success"] is True, result
        prs = Presentation(result["filepath"])
        fills = set()
        for sh in prs.slides[0].shapes:
            try:
                if sh.fill.type is not None:
                    fills.add(str(sh.fill.fore_color.rgb))
            except Exception:
                continue
        assert expected in fills, (theme, expected, fills)


def test_generic_themes_uncontaminated(tmp_path):
    """隔离边界：通用主题（aurora）不进入样张渲染器，画法保持原样。"""
    result = _run({"title": "隔离验证", "theme": "aurora",
                   "slides": [{"layout": "kpi", "heading": "指标",
                               "points": ["295亿|营收|+173%"]}]}, tmp_path)
    assert result["success"] is True, result
    assert result["data"]["theme"] == "aurora"
    # aurora KPI 走通用卡片画法（accent_light 浅紫卡），非样张数据带
    prs = Presentation(result["filepath"])
    fills = set()
    for sh in prs.slides[1].shapes:
        try:
            if sh.fill.type is not None:
                fills.add(str(sh.fill.fore_color.rgb))
        except Exception:
            continue
    assert "F6F4FF" in fills, "aurora KPI 应保留浅紫卡片"
