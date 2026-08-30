"""FTS 查询改写器：把用户输入转成精确/拼音两路 MATCH 查询。

纯函数模块，不触碰数据库。拼音判定基于标准普通话音节表做贪心最长
分词（与主流输入法习惯一致，接受 xian 这类合并歧义）。
"""

from __future__ import annotations

import re

# 标准普通话音节表（含 lv/nv/lue/nue 变体），用于分词与拼音合法性判定
_SYLLABLES = """
a ai an ang ao
ba bai ban bang bao bei ben beng bi bian biao bie bin bing bo bu
ca cai can cang cao ce cen ceng cha chai chan chang chao che chen
cheng chi chong chou chu chua chuai chuan chuang chui chun chuo ci
cong cou cu cuan cui cun cuo
da dai dan dang dao de den deng di dia dian diao die ding diu dong
dou du duan dui dun duo
e ei en eng er
fa fan fang fei fen feng fo fou fu
ga gai gan gang gao ge gei gen geng gong gou gu gua guai guan guang
gui gun guo
ha hai han hang hao he hei hen heng hong hou hu hua huai huan huang
hui hun huo
ji jia jian jiang jiao jie jin jing jiong jiu ju juan jue jun
ka kai kan kang kao ke kei ken keng kong kou ku kua kuai kuan kuang
kui kun kuo
la lai lan lang lao le lei leng li lia lian liang liao lie lin ling
liu lo long lou lu luan lun luo lv lue
ma mai man mang mao me mei men meng mi mian miao mie min ming miu mo
mou mu
na nai nan nang nao ne nei nen neng ni nian niang niao nie nin ning
niu nong nou nu nuan nuo nv nue
o ou
pa pai pan pang pao pei pen peng pi pian piao pie pin ping po pou pu
qi qia qian qiang qiao qie qin qing qiong qiu qu quan que qun
ran rang rao re ren reng ri rong rou ru rua ruan rui run ruo
sa sai san sang sao se sen seng sha shai shan shang shao she shei
shen sheng shi shou shu shua shuai shuan shuang shui shun shuo si
song sou su suan sui sun suo
ta tai tan tang tao te teng ti tian tiao tie ting tong tou tu tuan
tui tun tuo
wa wai wan wang wei wen weng wo wu
xi xia xian xiang xiao xie xin xing xiong xiu xu xuan xue xun
ya yan yang yao ye yi yin ying yo yong you yu yuan yue yun
za zai zan zang zao ze zei zen zeng zha zhai zhan zhang zhao zhe zhen
zheng zhi zhong zhou zhu zhua zhuai zhuan zhuang zhui zhun zhuo zi
zong zou zu zuan zui zun zuo
""".split()

_SYLLABLE_SET = frozenset(_SYLLABLES)
_ASCII_LETTERS_RE = re.compile(r"^[a-z]+$")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def segment_syllables(text: str) -> list[str] | None:
    """贪心最长分词；无法完全切分为音节时返回 None。"""
    result: list[str] = []
    index = 0
    while index < len(text):
        matched = None
        for end in range(min(index + 6, len(text)), index, -1):
            candidate = text[index:end]
            if candidate in _SYLLABLE_SET:
                matched = candidate
                index = end
                break
        if matched is None:
            return None
        result.append(matched)
    return result


def _compact(query: str) -> str:
    """去空格小写；含其他非字母字符时视为非拼音输入。"""
    q = query.strip().lower()
    compact = q.replace(" ", "")
    if not compact or not _ASCII_LETTERS_RE.match(compact):
        return ""
    return compact


def is_pinyin_query(query: str) -> bool:
    """纯小写字母（允许音节间空格）且（可完整切分，或 ≤4 字母可作缩写）。"""
    compact = _compact(query)
    if len(compact) < 2:
        return False
    if segment_syllables(compact) is not None:
        return True
    return len(compact) <= 4  # 首字母缩写，如 zs / wx


def build_pinyin_match(query: str) -> str | None:
    """构造拼音副表的 MATCH 表达式；输入不是拼音形态时返回 None。

    全部由 ASCII 字母组成（已校验），不存在 FTS 语法注入风险。
    """
    q = _compact(query)
    if len(q) < 2:
        return None
    syllables = segment_syllables(q)
    if syllables is None and len(q) > 4:
        # 既不可切分为音节、也不像首字母缩写 → 不是拼音形态
        return None
    forms: list[str] = [q, f"{q}*"]  # 连写 token 与前缀（覆盖正文里的英文词）
    if syllables:
        # 连续音节短语 + 末音节前缀
        forms.append(" ".join(syllables))
        forms.append(" ".join(syllables[:-1] + [f"{syllables[-1]}*"]))
    elif len(q) <= 4:
        # 首字母缩写："zs" → 首音节前缀短语
        forms.append(" ".join(f"{ch}*" for ch in q))
    # 最长可切分前缀的截断形态："zhif" → "zhi*"（半音节输入）
    for cut in range(len(q) - 1, 1, -1):
        prefix_seg = segment_syllables(q[:cut])
        if prefix_seg:
            forms.append(
                " ".join(prefix_seg[:-1] + [f"{prefix_seg[-1]}*"])
            )
            break
    # 去重保序
    seen: set[str] = set()
    unique = [f for f in forms if not (f in seen or seen.add(f))]
    return " OR ".join(unique)


def build_or_match(query: str) -> str | None:
    """中文多词查询 0 命中时的宽松召回：词间 AND 降级为 OR。"""
    terms = [
        term for term in re.split(r"\s+", query.strip()) if term
    ]
    if len(terms) < 2:
        return None
    quoted = []
    for term in terms:
        cleaned = term.replace('"', " ").strip()
        if cleaned:
            quoted.append(f'"{cleaned}"')
    return " OR ".join(quoted) if len(quoted) >= 2 else None


def is_short_query(query: str) -> bool:
    """trigram 下限是 3 字符；更短的查询需要 LIKE 兜底。"""
    return len(query.strip()) < 3


def has_cjk(query: str) -> bool:
    return bool(_CJK_RE.search(query))
