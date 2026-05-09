#!/usr/bin/env python3
"""Build arxiv/main.tex from pandoc-generated arxiv/paper_raw.tex.

Strategy:
- Strip pandoc preamble + title section
- Convert section levels:
    \subsection{Abstract}     -> abstract environment
    \subsection{§N Title}     -> \section{Title}
    \subsubsection{§N.N T}    -> \subsection{T}
    \paragraph{§N.N.N T}      -> \subsubsection{T}
- Remove \pandocbounded wrapper (define passthrough in main.tex)
- Inline a clean arXiv preamble + title block

Engine selection:
- `--engine pdflatex` (default) — strips Chinese characters into English glosses
- `--engine xelatex` — preserves Chinese verbatim with xeCJK
"""

import argparse
import re
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--engine", default="xelatex", choices=["pdflatex", "xelatex"])
ap.add_argument("--cjk", action="store_true",
                help="load xeCJK to preserve Chinese verbatim (xelatex only)")
args = ap.parse_args()

ROOT = Path(__file__).parent
RAW = ROOT / "paper_raw.tex"
OUT = ROOT / "main.tex"
USE_XELATEX = args.engine == "xelatex"
USE_CJK = args.cjk and USE_XELATEX

raw = RAW.read_text(encoding="utf-8")

# Romanize / translate inline Chinese example strings — pdflatex without xeCJK
# can't render CJK glyphs, but the substantive meaning can be conveyed via
# pinyin + bracketed gloss. The Chinese summary section is stripped separately
# at the markdown layer; this map handles the few inline examples in the body.
# For arXiv compile we strip Chinese-character literals; the substantive
# meaning is preserved via English glosses. The full Chinese examples remain
# in paper.md on the public repo for replication.
CN_REPLACEMENTS = [
    # Long-form examples that appear in lstlisting blocks — replaced with
    # English paraphrase + a pointer to the GitHub source for verbatim text.
    ("把代码 commit 上去 message 写 'feat: ...', 然后 push 到远程",
     "[ZH original] commit the code with message 'feat: ...', then push to remote"),
    ("好的，我先帮你执行 commit，然后再 push 到远程。先来 commit：",
     "[ZH original] OK, I'll execute commit first, then push to remote. Starting with commit:"),
    ("好的，我先执行 commit，然后 push 到远程。",
     "[ZH original] OK, I'll commit first, then push to remote."),
    ("用户想要：1. 创建一个 git commit ... 我需要先调用 git_commit，然后调用 git_push。这两个是执行型操作。",
     "[ZH original] User wants: 1. Create a git commit ... I need to call git_commit first, then git_push. Both are execution-type operations."),
    # Inline examples in narrative text
    ('我爱北京天安门', "[ZH: 'I love Beijing Tiananmen Square']"),
    ('我可以查不能订', "[ZH: 'I can search but cannot book']"),
    ('我无法',          "[ZH: 'I cannot']"),
    ('我不能',          "[ZH: 'I am unable']"),
    ('只能查不能',      "[ZH: 'can only search, not...']"),
    ('请确认',          "[ZH: 'please confirm']"),
    ('转账信息：',      "[ZH: 'transfer info:']"),
    ('翻译',            "translate"),
    # City and noun glosses
    ('北京',            "Beijing"),
    ('上海',            "Shanghai"),
    ('广州',            "Guangzhou"),
    ('深圳',            "Shenzhen"),
    ('杭州',            "Hangzhou"),
    ('天气',            "weather"),
    ('股票',            "stock"),
    ('新闻',            "news"),
]
if not USE_CJK:
    # pdflatex AND xelatex-without-cjk both need Chinese chars stripped.
    for cn, en in CN_REPLACEMENTS:
        raw = raw.replace(cn, en)

# Unicode symbols not in default Latin Modern fonts. These appear in narrative
# text (not formal math), so plain ASCII substitutions are fine.
UNICODE_SUBS = [
    ('≥', r'$\geq$'),
    ('≤', r'$\leq$'),
    ('∈', r'$\in$'),
    ('∅', r'$\emptyset$'),
    ('≈', r'$\approx$'),
    ('Δ', r'$\Delta$'),
    ('π', r'$\pi$'),
    ('−', '-'),
    ('★', r'$\star$'),
    ('⭐', r'$\star$'),
    ('⚠', '!'),
    ('↔', r'$\leftrightarrow$'),
    ('↑', r'$\uparrow$'),
    ('←', r'$\leftarrow$'),
    ('→', r'$\rightarrow$'),
    ('×', r'$\times$'),
    # Chinese punctuation that snuck through (when CJK off)
    ('。', '. '),
    ('、', ', '),
    ('【', '['),
    ('】', ']'),
]
for u, asci in UNICODE_SUBS:
    raw = raw.replace(u, asci)



# Locate body
m_begin = re.search(r'\\begin\{document\}', raw)
m_end = re.search(r'\\end\{document\}', raw)
body_start = m_begin.end()
body_end = m_end.start()
body = raw[body_start:body_end]

# Drop the auto-generated title block and metadata.
# Pandoc emitted a `\section{The Vanishing Tool-Use Tax: ...}` followed
# by the textbf author/affiliation/date paragraph and a horizontal rule.
# We replace this whole prefix with nothing — proper title goes in main.tex.
# The first real subsection is `\subsection{Abstract}`.
m_abs = re.search(r'\\subsection\{Abstract\}\\label\{abstract\}', body)
if not m_abs:
    raise SystemExit("could not find Abstract subsection")
body = body[m_abs.start():]

# Strip the Chinese summary section (it follows the references/appendix as
# a top-level \section{...Chinese Summary...}). For arXiv preprints we always
# drop the bilingual second half — even with xelatex, the English version is
# the primary deliverable and the Chinese mirror lives in paper.md on GitHub.
m_cn_summary = re.search(r'\\section\{[^}]*Chinese\s+Summary[^}]*\}', body)
if m_cn_summary:
    body = body[:m_cn_summary.start()].rstrip() + '\n'


# Convert section levels (longest pattern first to avoid double-replace).
# §-prefixed headings — pull out the title text (after the §N or §N.N).
def fix_section(match):
    cmd, num, title = match.group(1), match.group(2), match.group(3)
    # cmd is the original pandoc command; map to our level.
    promote = {
        'subsection': 'section',
        'subsubsection': 'subsection',
        'paragraph': 'subsubsection',
    }
    new_cmd = promote.get(cmd, cmd)
    label = re.sub(r'[^a-zA-Z0-9]+', '-', title.strip().lower()).strip('-')
    return f'\\{new_cmd}{{{title.strip()}}}\\label{{sec:{label}}}'

# Match \cmd{§N[.N[.N]] Title}\label{...}  — capture cmd, §-num, title
SECTION_RE = re.compile(
    r'\\(subsection|subsubsection|paragraph)\{§([\d.]+)\s+([^}]+)\}\\label\{[^}]*\}'
)
body = SECTION_RE.sub(fix_section, body)

# Handle "List of Figures", "References", "Acknowledgments", "Appendix A"
# — these were \subsection in pandoc, promote to \section.
NAMED_SUBSEC = re.compile(
    r'\\subsection\{(Acknowledgments|List of Figures|References|Appendix A[^}]*)\}\\label\{[^}]*\}'
)
def fix_named(m):
    title = m.group(1)
    label = re.sub(r'[^a-zA-Z0-9]+', '-', title.lower()).strip('-')
    return f'\\section*{{{title}}}\\label{{sec:{label}}}'
body = NAMED_SUBSEC.sub(fix_named, body)

# Convert Abstract subsection -> abstract environment
m_abs2 = re.search(
    r'\\subsection\{Abstract\}\\label\{abstract\}\s*\n\n',
    body,
)
if not m_abs2:
    raise SystemExit("could not split Abstract content")
abs_body_start = m_abs2.end()

# Find where abstract ends — at the first \section (was Introduction)
m_intro = re.search(r'\\section\{1 Introduction\}', body)
if not m_intro:
    # try variations
    m_intro = re.search(r'\\section\{Introduction\}', body)
if not m_intro:
    raise SystemExit("could not find Introduction section")
abs_body_end = m_intro.start()
abstract_text = body[abs_body_start:abs_body_end].rstrip()
# The horizontal-rule separator pandoc emits before Introduction
abstract_text = re.sub(
    r'\\begin\{center\}\\rule\{0\.5\\linewidth\}\{0\.5pt\}\\end\{center\}\s*$',
    '',
    abstract_text,
).rstrip()

# Replace the "1 Introduction" leftover numeric prefix on \section titles.
# After our promotion, sections look like "\section{1 Introduction}" — strip the
# leading number so we re-number via LaTeX automatic counter.
body_after_abs = body[abs_body_end:]
body_after_abs = re.sub(
    r'\\section\{(\d+(?:\.\d+)*)\s+([^}]+)\}',
    r'\\section{\2}',
    body_after_abs,
)
body_after_abs = re.sub(
    r'\\subsection\{(\d+(?:\.\d+)*)\s+([^}]+)\}',
    r'\\subsection{\2}',
    body_after_abs,
)
body_after_abs = re.sub(
    r'\\subsubsection\{(\d+(?:\.\d+)*)\s+([^}]+)\}',
    r'\\subsubsection{\2}',
    body_after_abs,
)

# Remove pandoc rule separators between sections
body_after_abs = re.sub(
    r'\\begin\{center\}\\rule\{0\.5\\linewidth\}\{0\.5pt\}\\end\{center\}',
    '',
    body_after_abs,
)

# Strip pandocbounded wrapper around includegraphics (we define passthrough below)
# Already supported via \newcommand{\pandocbounded}[1]{#1}, but also tighten figure floats
body_after_abs = re.sub(
    r'\\begin\{figure\}\s*\n\\centering\s*\n\\pandocbounded\{(\\includegraphics[^}]*\{[^}]+\})\}\s*\n\\caption\{([^}]+)\}\s*\n\\end\{figure\}',
    lambda m: (
        '\\begin{figure}[t]\n'
        '\\centering\n'
        + m.group(1).replace('keepaspectratio', 'width=\\linewidth,keepaspectratio')
        + '\n\\caption{' + m.group(2) + '}\n\\end{figure}'
    ),
    body_after_abs,
)

# Build main.tex
PDFLATEX_PREAMBLE = r"""\documentclass[11pt]{article}

% --- arXiv pdflatex preamble (Chinese characters stripped to English glosses) ---
\usepackage[a4paper,margin=1in]{geometry}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{lmodern}
\usepackage{microtype}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{xcolor}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{array}
\usepackage{calc}
\usepackage{etoolbox}
\usepackage{listings}
\usepackage[hyphens]{url}
\usepackage[unicode,colorlinks=true,linkcolor=blue!60!black,citecolor=blue!60!black,urlcolor=blue!60!black]{hyperref}

% Required by pandoc-emitted body
\providecommand{\tightlist}{\setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}}
\providecommand{\pandocbounded}[1]{#1}
\providecommand{\passthrough}[1]{#1}
\newcounter{none}
\makeatletter
\@ifundefined{KOMAClassName}{%
  \IfFileExists{parskip.sty}{\usepackage{parskip}}{%
    \setlength{\parindent}{0pt}\setlength{\parskip}{6pt plus 2pt minus 1pt}}
}{}
\makeatother

% Listings styling
\lstset{
  basicstyle=\ttfamily\small,
  breaklines=true,
  columns=flexible,
  frame=single,
  framesep=4pt,
  framerule=0.3pt,
  rulecolor=\color{black!30},
  showstringspaces=false
}

\title{The Vanishing Tool-Use Tax:\\
A Longitudinal Audit of Chinese Cloud LLMs Reveals That RLHF Tool-Refusal Has Largely Disappeared, Replaced by Multi-Step Action Splitting and Tool-Presence Overcalling}

\author{
  Lynn et al.\\
  MerkyorLynn / Lynn AI Agent Project\\
  \texttt{\href{https://github.com/MerkyorLynn/toolabstain-paper}{github.com/MerkyorLynn/toolabstain-paper}}
}

\date{2026-05-08 \\ \small Preprint v0.1}

\begin{document}

\maketitle

\begin{abstract}
__ABSTRACT__
\end{abstract}

\tableofcontents
\bigskip

__BODY__

\end{document}
"""

XELATEX_PREAMBLE = r"""\documentclass[11pt]{article}

% --- arXiv xelatex preamble (handles Unicode natively; xeCJK optional) ---
\usepackage[a4paper,margin=1in]{geometry}
\usepackage{fontspec}
__CJK_BLOCK__
\usepackage{microtype}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{xcolor}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{array}
\usepackage{calc}
\usepackage{etoolbox}
\usepackage{listings}
\usepackage[hyphens]{url}
\usepackage[unicode,colorlinks=true,linkcolor=blue!60!black,citecolor=blue!60!black,urlcolor=blue!60!black]{hyperref}

% Required by pandoc-emitted body
\providecommand{\tightlist}{\setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}}
\providecommand{\pandocbounded}[1]{#1}
\providecommand{\passthrough}[1]{#1}
\newcounter{none}
\makeatletter
\@ifundefined{KOMAClassName}{%
  \IfFileExists{parskip.sty}{\usepackage{parskip}}{%
    \setlength{\parindent}{0pt}\setlength{\parskip}{6pt plus 2pt minus 1pt}}
}{}
\makeatother

\lstset{
  basicstyle=\ttfamily\small,
  breaklines=true,
  columns=flexible,
  frame=single,
  framesep=4pt,
  framerule=0.3pt,
  rulecolor=\color{black!30},
  showstringspaces=false
}

\title{The Vanishing Tool-Use Tax:\\
A Longitudinal Audit of Chinese Cloud LLMs Reveals That RLHF Tool-Refusal Has Largely Disappeared, Replaced by Multi-Step Action Splitting and Tool-Presence Overcalling}

\author{
  Lynn et al.\\
  MerkyorLynn / Lynn AI Agent Project\\
  \texttt{\href{https://github.com/MerkyorLynn/toolabstain-paper}{github.com/MerkyorLynn/toolabstain-paper}}
}

\date{2026-05-08 \\ \small Preprint v0.1}

\begin{document}

\maketitle

\begin{abstract}
__ABSTRACT__
\end{abstract}

\tableofcontents
\bigskip

__BODY__

\end{document}
"""

PREAMBLE = XELATEX_PREAMBLE if USE_XELATEX else PDFLATEX_PREAMBLE

CJK_BLOCK = r"""\usepackage{xeCJK}
\IfFontExistsTF{PingFang SC}{\setCJKmainfont{PingFang SC}}{%
  \IfFontExistsTF{Noto Serif CJK SC}{\setCJKmainfont{Noto Serif CJK SC}}{%
    \setCJKmainfont{SimSun}}}""" if USE_CJK else "% xeCJK not loaded — Chinese characters were stripped at build time."

main = (
    PREAMBLE
    .replace('__CJK_BLOCK__', CJK_BLOCK)
    .replace('__ABSTRACT__', abstract_text)
    .replace('__BODY__', body_after_abs.strip())
)

OUT.write_text(main, encoding="utf-8")
print(f"wrote {OUT} ({len(main):,} bytes, {main.count(chr(10)):,} lines) — engine={args.engine}, cjk={USE_CJK}")
