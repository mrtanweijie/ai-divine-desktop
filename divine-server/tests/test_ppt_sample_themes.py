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
    """样张节奏：首个 section 保留为深色使命宣言页（015/016 P2）；
    多余 section 与 toc 页跳过（含显式 toc=true）。"""
    for theme in ("devconf", "keynote"):
        result = _run({"title": "样张主题", "theme": theme, "toc": True,
                       "slides": _FULL_DECK}, tmp_path)
        assert result["success"] is True, result
        data = result["data"]
        # 14 页输入 - toc = 13 页（首个 section 保留；不含自动补齐项）
        assert data["slides"] == 13, theme
        assert not any("章节页" in w for w in data["warnings"]), theme
        assert any("目录页" in w for w in data["warnings"]), theme
        # 首个 section = 深色使命宣言页且被保留（签名按主题：devconf 页脚
        # BRAND MANIFESTO；keynote 断言其标题文本仍存在于页序中）
        prs = Presentation(result["filepath"])
        all_txt = "\n".join(sh.text_frame.text for s in prs.slides
                            for sh in s.shapes if sh.has_text_frame)
        assert "应被跳过的章节页" in all_txt, theme
        if theme == "devconf":
            assert "BRAND MANIFESTO" in all_txt, theme


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
    # 表格：mono 大写表头（016 P10）
    tables = [sh.table for slide in prs.slides for sh in slide.shapes
              if sh.has_table]
    assert tables
    header = [tables[0].cell(0, c).text
              for c in range(len(tables[0].columns))]
    # 表头内容完整、无 accent 色块（表头填充=纸白底色）
    assert header == ["能力", "我们"]
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
    # mono 页码 + 进度点页脚（015 签名）
    assert "02 / 13" in texts(prs.slides[1])
    # 编号行（015 大字排版承载要点/里程碑）
    assert "01" in texts(prs.slides[1])


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
