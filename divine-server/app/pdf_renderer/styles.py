"""Shared PDF style tokens and page CSS template."""

from __future__ import annotations

from string import Template

STYLE_KEYS = ("modern", "academic", "corporate", "minimal", "playful")

COLOR_KEYS = ("blue", "green", "warm", "monochrome", "purple")

PAPER_KEYS = ("a4", "letter", "legal")

COLOR_MAP = {
    "blue": {"accent": "#2563eb", "light": "#eaf1fe", "dark": "#1e40af"},
    "green": {"accent": "#15803d", "light": "#ecfdf3", "dark": "#14532d"},
    "warm": {"accent": "#c2570a", "light": "#fff4e5", "dark": "#9a3412"},
    "monochrome": {"accent": "#111827", "light": "#f3f4f6", "dark": "#111827"},
    "purple": {"accent": "#6d28d9", "light": "#f3e8ff", "dark": "#5b21b6"},
}

_STYLE_FONT = {
    "academic": '"Songti SC", "STSong", "Noto Serif CJK SC", serif',
    "playful": '"PingFang SC", "Microsoft YaHei", sans-serif',
    "corporate": '"PingFang SC", "Microsoft YaHei", sans-serif',
    "minimal": '"PingFang SC", "Microsoft YaHei", sans-serif',
    "modern": '"Noto Sans SC", "Source Han Sans CN", "PingFang SC", sans-serif',
}

_PAGE_CSS = Template(
    """
@page {
  size: $paper;
  margin: 2.2cm 2cm 2.5cm 2cm;
  @top-center {
    content: element(header);
    border-bottom: 0.5pt solid #e0e0e0;
    padding-bottom: 4pt;
  }
  @bottom-center {
    content: counter(page) " / " counter(pages);
    font-size: 8.5pt;
    color: #999;
    font-family: $font_family;
  }
}
body {
  font-family: $font_family;
  font-size: 10.5pt;
  line-height: 1.85;
  color: #2c2c2c;
}
h1 {
  font-size: 24pt;
  font-weight: 700;
  color: #1a1a2e;
  margin-top: 0;
  margin-bottom: 0.4em;
  line-height: 1.3;
  letter-spacing: -0.02em;
}
h2 {
  font-size: 16pt;
  font-weight: 600;
  color: $accent;
  margin-top: 2em;
  margin-bottom: 0.6em;
  padding-left: 0.6em;
  border-left: 4pt solid $accent;
  line-height: 1.4;
  page-break-after: avoid;
}
h3 {
  font-size: 13pt;
  font-weight: 600;
  color: #333;
  margin-top: 1.5em;
  margin-bottom: 0.4em;
  page-break-after: avoid;
}
h4 {
  font-size: 11pt;
  font-weight: 600;
  color: #555;
  margin-top: 1.2em;
}
p {
  margin: 0.6em 0;
  orphans: 2;
  widows: 2;
}
ul, ol {
  margin: 0.6em 0;
  padding-left: 1.4em;
}
li {
  margin: 0.35em 0;
  padding-left: 0.2em;
}
li::marker {
  color: $accent;
  font-weight: 600;
}
.illustration,
figure {
  text-align: center;
  margin: 1.8em auto;
  page-break-inside: avoid;
  page-break-after: avoid;
}
.illustration img,
figure img,
.illustration svg {
  max-width: 82%;
  height: auto;
  border-radius: 6px;
  box-shadow: 0 3px 14px rgba(0, 0, 0, 0.10);
}
figcaption,
.illustration .caption {
  font-size: 8.5pt;
  color: #888;
  margin-top: 0.5em;
  font-style: italic;
}
pre {
  background: #f6f8fa;
  border: 1pt solid #e1e4e8;
  border-radius: 6px;
  padding: 1em 1.2em;
  margin: 1.2em 0;
  font-size: 9pt;
  line-height: 1.55;
  overflow-x: auto;
  page-break-inside: avoid;
}
code {
  font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
  font-size: 8.5pt;
  background: #f0f2f5;
  padding: 1pt 4pt;
  border-radius: 3pt;
}
pre code {
  background: none;
  padding: 0;
}
blockquote {
  border-left: 3pt solid $accent;
  background: $light;
  margin: 1.2em 0;
  padding: 0.8em 1.2em;
  border-radius: 0 6px 6px 0;
  color: #444;
  font-style: italic;
  page-break-inside: avoid;
}
table {
  width: 100%;
  border-collapse: collapse;
  margin: 1.5em 0;
  font-size: 9.5pt;
  page-break-inside: auto;
}
thead {
  background: $accent;
  color: white;
}
th, td {
  padding: 0.5em 0.8em;
  border: 0.5pt solid #ddd;
  text-align: left;
}
tbody tr:nth-child(even) {
  background: #f9fafb;
}
a {
  color: $accent;
  text-decoration: none;
  border-bottom: 0.5pt dotted $accent;
}
.cover {
  page-break-after: always;
  text-align: center;
  padding-top: 28vh;
}
.cover h1 {
  font-size: 32pt;
  letter-spacing: -0.03em;
}
.cover .subtitle {
  font-size: 14pt;
  color: #666;
  margin-top: 0.8em;
  font-weight: 300;
}
.cover .meta {
  margin-top: 2.5em;
  font-size: 9.5pt;
  color: #aaa;
}
.running-header {
  position: running(header);
  font-size: 8.5pt;
  color: #888;
}
.resource-card {
  border: 1pt solid #e0e0e0;
  border-radius: 6px;
  padding: 0.7em 1em;
  margin: 0.8em 0;
  background: #fafbfc;
  page-break-inside: avoid;
}
.resource-card .tag {
  display: inline-block;
  font-size: 7.5pt;
  font-weight: 600;
  padding: 1pt 6pt;
  border-radius: 3pt;
  background: $light;
  color: $accent;
  margin-right: 0.5em;
}
h1, h2, h3, h4 {
  orphans: 2;
  widows: 2;
}
"""
)
