"""
Markdown 학습 노트 → HTML 대시보드 변환기
- 사이드바 TOC + 검색 + 접이식 섹션 + 다크모드
- 3-Line Summary / 요약 / Implications는 상위 섹션에 종속
"""

import re
import html
import sys
import shutil
from urllib.parse import quote
from pathlib import Path

IMAGE_URLS = {}


def parse_sections(md_text: str) -> list[dict]:
    """마크다운을 섹션 단위로 파싱. 3-Line Summary/요약은 부모에 병합."""
    lines = md_text.split('\n')
    sections = []
    current = None
    in_sub = False  # 3-line summary나 요약 하위인지

    # frontmatter 스킵
    i = 0
    if lines and lines[0].strip() == '---':
        i = 1
        while i < len(lines) and lines[i].strip() != '---':
            i += 1
        i += 1

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # ## 헤딩 감지
        h2_match = re.match(r'^##\s+(.+)', line)
        h3_match = re.match(r'^###\s+(.+)', line)

        # ### [[노트링크]]는 임베드된 독립 노트: 섹션으로 승격 (TOC 노출)
        if h3_match:
            t3 = h3_match.group(1).strip()
            if re.fullmatch(r'\[\[[^\]]+\]\]', t3) and not is_sub_section(t3):
                h2_match, h3_match = h3_match, None

        if h2_match:
            title = h2_match.group(1).strip()
            # 3-Line Summary나 요약은 부모에 병합
            if current and is_sub_section(title):
                if in_sub:
                    current['body'] += '</div>\n'
                in_sub = True
                current['body'] += f'\n<div class="sub-section sub-summary"><h4>{html.escape(clean_title(title))}</h4>\n'
                i += 1
                continue
            else:
                # 이전 서브섹션 닫기
                if current and in_sub:
                    current['body'] += '</div>\n'
                    in_sub = False
                # 새 섹션 시작
                if current:
                    sections.append(current)
                current = {
                    'title': clean_title(title),
                    'raw_title': title,
                    'body': '',
                    'id': f'section-{len(sections)}'
                }
                i += 1
                continue

        if h3_match and current:
            title = h3_match.group(1).strip()
            if is_sub_section(title):
                if in_sub:
                    current['body'] += '</div>\n'
                in_sub = True
                current['body'] += f'\n<div class="sub-section sub-summary"><h4>{html.escape(clean_title(title))}</h4>\n'
                i += 1
                continue
            else:
                if in_sub:
                    current['body'] += '</div>\n'
                    in_sub = False
                current['body'] += f'<h4>{html.escape(clean_title(title))}</h4>\n'
                i += 1
                continue

        # --- 구분선이면 sub-summary 닫기
        if in_sub and stripped == '---':
            current['body'] += '</div>\n'
            in_sub = False
            i += 1
            continue

        # 본문 처리 (들여쓰기 보존을 위해 rstrip만 한 원본 줄을 넘긴다)
        if current:
            current['body'] += process_line(line.rstrip()) + '\n'

        i += 1

    if current:
        if in_sub:
            current['body'] += '</div>\n'
        sections.append(current)

    return sections


def is_sub_section(title: str) -> bool:
    # 제목 전체가 요약 헤딩일 때만 병합 (부분 포함 매칭은 '..._주간_요약' 같은 독립 노트를 삼킴)
    t = clean_title(title).lower().strip('*: ').strip()
    return t in ('3-line summary', '3 line summary', '요약', 'implications', '임플리케이션')


def clean_title(title: str) -> str:
    """Obsidian [[]] 링크, ** 등 정리"""
    title = re.sub(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]', lambda m: m.group(2) or m.group(1), title)
    title = title.replace('**', '').replace('****', '').strip()
    # 이모지는 유지
    return title


def process_line(line: str) -> str:
    """한 줄을 HTML로 변환. line은 rstrip만 된 상태 (좌측 들여쓰기 유지)"""
    stripped = line.strip()
    if not stripped:
        return '<br>'

    image_match = re.match(r'^!\[\[([^|\]]+)(?:\|([^\]]+))?\]\]$', stripped)
    if image_match:
        name = image_match.group(1).strip()
        alt = Path(name).stem
        src = IMAGE_URLS.get(name)
        if src:
            return f'<figure class="note-image"><img src="{html.escape(src)}" alt="{html.escape(alt)}" loading="lazy"></figure>'
        return f'<div class="missing-image">이미지를 찾을 수 없음: {html.escape(name)}</div>'

    md_image_match = re.match(r'^!\[([^\]]*)\]\(([^)]+)\)$', stripped)
    if md_image_match:
        alt = md_image_match.group(1).strip()
        name = md_image_match.group(2).strip()
        src = IMAGE_URLS.get(name) or name
        return f'<figure class="note-image"><img src="{html.escape(src)}" alt="{html.escape(alt)}" loading="lazy"></figure>'

    # 블록쿼트 (내부 들여쓰기: '> \t- ...' 형태는 indent 클래스)
    if stripped.startswith('>'):
        inner = stripped.lstrip('>')
        if inner.startswith(' '):
            inner = inner[1:]
        is_indent = inner.startswith(('\t', '  '))
        content = inline_format(html.escape(inner.strip()))
        cls = 'quote-line indent' if is_indent else 'quote-line'
        return f'<div class="{cls}">{content}</div>'

    # 들여쓴 리스트 (원본 줄의 좌측 공백으로 판정: 비들여쓰기보다 먼저 검사)
    indent_match = re.match(r'^(\t+|\s{2,})(\d+)\.\s+(.+)', line)
    if indent_match:
        content = inline_format(html.escape(indent_match.group(3)))
        return f'<div class="memo-item indent">{indent_match.group(2)}. {content}</div>'

    indent_ul_match = re.match(r'^(\t+|\s{2,})[-*]\s+(.+)', line)
    if indent_ul_match:
        content = inline_format(html.escape(indent_ul_match.group(2)))
        return f'<div class="memo-bullet indent">• {content}</div>'

    # 순서 리스트
    ol_match = re.match(r'^(\d+)\.\s+(.+)', stripped)
    if ol_match:
        content = inline_format(html.escape(ol_match.group(2)))
        return f'<div class="memo-item"><span class="memo-num">{ol_match.group(1)}.</span> {content}</div>'

    # 비순서 리스트
    ul_match = re.match(r'^[-*]\s+(.+)', stripped)
    if ul_match:
        content = inline_format(html.escape(ul_match.group(1)))
        return f'<div class="memo-bullet">• {content}</div>'

    # 테이블 (간단 처리)
    if '|' in stripped and stripped.startswith('|'):
        cells = [c.strip() for c in stripped.split('|')[1:-1]]
        if all(re.match(r'^[-:]+$', c) for c in cells):
            return ''  # 구분선 스킵
        row = ''.join(f'<td>{inline_format(html.escape(c))}</td>' for c in cells)
        return f'<tr>{row}</tr>'

    # 볼드 텍스트 라인
    if stripped.startswith('**') and stripped.endswith('**'):
        content = inline_format(html.escape(stripped.strip('*').strip()))
        cls = 'bold-line indent' if line[:1] in (' ', '\t') else 'bold-line'
        return f'<div class="{cls}">{content}</div>'

    # 일반 텍스트 (들여쓴 일반 줄도 indent 유지)
    content = inline_format(html.escape(stripped))
    cls = 'text-line indent' if line[:1] in (' ', '\t') else 'text-line'
    return f'<div class="{cls}">{content}</div>'


def inline_format(text: str) -> str:
    """인라인 서식 (볼드, 이탤릭, 하이라이트, 링크)"""
    # ==하이라이트==
    text = re.sub(r'==(.+?)==', r'<mark>\1</mark>', text)
    # **볼드**
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # *이탤릭*
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    # [[위키링크]]
    text = re.sub(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]', lambda m: f'<span class="wiki-link">{m.group(2) or m.group(1)}</span>', text)
    return text


def extract_image_refs(md_text: str) -> list[str]:
    refs = []
    seen = set()
    patterns = [
        r'!\[\[([^|\]]+)(?:\|[^\]]+)?\]\]',
        r'!\[[^\]]*\]\(([^)]+)\)',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, md_text):
            name = match.group(1).strip()
            if name and name not in seen:
                seen.add(name)
                refs.append(name)
    return refs


def find_vault_root(src: Path) -> Path:
    for parent in [src.parent, *src.parents]:
        if parent.name == 'default vaultrealrealreal':
            return parent
    return src.parents[0]


def prepare_images(md_text: str, src: Path, out_dir: Path) -> dict[str, str]:
    refs = extract_image_refs(md_text)
    if not refs:
        return {}

    vault_root = find_vault_root(src)
    image_dir = vault_root / '90. ARCHIVE (완료)' / '901. IMAGE'
    assets_dir = out_dir / 'assets' / 'images'
    assets_dir.mkdir(parents=True, exist_ok=True)

    urls = {}
    copied = 0
    missing = []
    for ref in refs:
        filename = Path(ref).name
        candidates = []
        direct = image_dir / filename
        if direct.exists():
            candidates.append(direct)
        else:
            candidates.extend(vault_root.rglob(filename))

        if not candidates:
            missing.append(ref)
            continue

        source = candidates[0]
        target = assets_dir / filename
        shutil.copy2(source, target)
        urls[ref] = f'assets/images/{quote(filename)}'
        urls[filename] = urls[ref]
        copied += 1

    print(f"  {copied} images copied")
    if missing:
        print(f"  {len(missing)} images missing: {', '.join(missing[:5])}")

    return urls


def make_title(src: Path) -> str:
    """소스 파일명에서 페이지 제목 추출 ('~' 뒤 부연은 버림)"""
    return src.stem.split('~')[0].strip()


def generate_html(sections: list[dict], title: str) -> str:
    """섹션 리스트를 HTML 대시보드로 변환"""

    # TOC 생성
    toc_items = []
    for i, sec in enumerate(sections):
        title_short = sec['title'][:40] + ('...' if len(sec['title']) > 40 else '')
        toc_items.append(
            f'<li><a href="#{sec["id"]}" class="toc-link" data-index="{i}">'
            f'<span class="toc-num">{i+1:02d}</span>{html.escape(title_short)}</a></li>'
        )
    toc_html = '\n'.join(toc_items)

    # 섹션 콘텐츠 생성
    section_cards = []
    for i, sec in enumerate(sections):
        body = sec['body']
        # 연속 quote-line을 blockquote로 래핑
        body = wrap_quotes(body)
        # 테이블 래핑
        body = wrap_tables(body)

        section_cards.append(f'''
        <div class="section-card" id="{sec['id']}" data-index="{i}">
            <div class="section-header" role="button" tabindex="0" onclick="toggleSection(this)" onkeydown="if(event.key==='Enter'||event.key===' '){{event.preventDefault();toggleSection(this);}}">
                <span class="section-num">{i+1:02d}</span>
                <h2 class="section-title">{html.escape(sec['title'])}</h2>
                <span class="toggle-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></span>
            </div>
            <div class="section-body">
                {body}
            </div>
        </div>''')
    sections_html = '\n'.join(section_cards)

    return (HTML_TEMPLATE.replace('{{TOC}}', toc_html)
            .replace('{{SECTIONS}}', sections_html)
            .replace('{{COUNT}}', str(len(sections)))
            .replace('{{TITLE}}', html.escape(title)))


def wrap_quotes(body: str) -> str:
    """연속된 quote-line들을 blockquote로 묶기"""
    lines = body.split('\n')
    result = []
    in_quote = False
    for line in lines:
        if '<div class="quote-line">' in line:
            if not in_quote:
                result.append('<blockquote class="source-quote">')
                in_quote = True
            result.append(line)
        else:
            if in_quote:
                result.append('</blockquote>')
                in_quote = False
            result.append(line)
    if in_quote:
        result.append('</blockquote>')
    return '\n'.join(result)


def wrap_tables(body: str) -> str:
    """연속 <tr>을 <table>로 래핑"""
    lines = body.split('\n')
    result = []
    in_table = False
    for line in lines:
        if '<tr>' in line:
            if not in_table:
                result.append('<table class="data-table">')
                in_table = True
            result.append(line)
        else:
            if in_table:
                result.append('</table>')
                in_table = False
            result.append(line)
    if in_table:
        result.append('</table>')
    return '\n'.join(result)


HTML_TEMPLATE = r'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{TITLE}}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<style>
/* Hallmark · genre: editorial · macrostructure: Long Document · design-system: design.md · designed-as-app
 * theme: custom (paper oklch(96.5% 0.012 90) · accent oklch(52% 0.15 35) vermilion · Noto Serif KR + Pretendard) */
:root {
    --color-paper: oklch(96.5% 0.012 90);
    --color-paper-2: oklch(98.5% 0.006 90);
    --color-paper-3: oklch(94% 0.014 88);
    --color-ink: oklch(24% 0.012 60);
    --color-ink-2: oklch(47% 0.014 60);
    --color-rule: oklch(87% 0.012 85);
    --color-accent: oklch(52% 0.15 35);
    --color-accent-wash: oklch(93.5% 0.03 40);
    --color-focus: oklch(52% 0.15 35);
    --quote-bg: oklch(94.5% 0.012 88);
    --quote-rule: oklch(80% 0.02 80);
    --memo-bg: oklch(95% 0.035 95);
    --memo-rule: oklch(76% 0.09 90);
    --summary-bg: oklch(95% 0.025 150);
    --summary-rule: oklch(72% 0.08 150);
    --summary-head: oklch(44% 0.09 150);
    --highlight-bg: oklch(90% 0.12 95);
    --highlight-ink: oklch(26% 0.05 80);
    --search-hl-bg: oklch(83% 0.14 85);
    --search-hl-ink: oklch(22% 0.04 80);
    --missing-bg: oklch(95% 0.02 25);
    --missing-rule: oklch(85% 0.06 25);
    --missing-ink: oklch(45% 0.14 25);
    --wiki-link: oklch(52% 0.15 35);
    --shadow: 0 1px 3px oklch(20% 0.01 60 / 0.1);
    --font-display: 'Noto Serif KR', 'Apple SD Gothic Neo', 'Nanum Myeongjo', serif;
    --font-body: 'Pretendard Variable', Pretendard, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
    --dur-short: 160ms;
    --dur-med: 250ms;
}
[data-theme="dark"] {
    --color-paper: oklch(22% 0.012 60);
    --color-paper-2: oklch(25.5% 0.012 60);
    --color-paper-3: oklch(19.5% 0.012 60);
    --color-ink: oklch(90% 0.008 90);
    --color-ink-2: oklch(66% 0.012 80);
    --color-rule: oklch(33% 0.012 60);
    --color-accent: oklch(71% 0.13 40);
    --color-accent-wash: oklch(31% 0.045 40);
    --color-focus: oklch(71% 0.13 40);
    --quote-bg: oklch(25% 0.012 70);
    --quote-rule: oklch(42% 0.02 75);
    --memo-bg: oklch(27% 0.035 95);
    --memo-rule: oklch(55% 0.08 90);
    --summary-bg: oklch(25% 0.03 150);
    --summary-rule: oklch(48% 0.07 150);
    --summary-head: oklch(75% 0.1 150);
    --highlight-bg: oklch(45% 0.09 90);
    --highlight-ink: oklch(95% 0.02 95);
    --search-hl-bg: oklch(55% 0.12 80);
    --search-hl-ink: oklch(98% 0.005 90);
    --missing-bg: oklch(26% 0.03 25);
    --missing-rule: oklch(42% 0.08 25);
    --missing-ink: oklch(75% 0.11 25);
    --wiki-link: oklch(71% 0.13 40);
    --shadow: 0 1px 3px oklch(0% 0 0 / 0.35);
}

* { margin:0; padding:0; box-sizing:border-box; }

body {
    font-family: var(--font-body);
    background: var(--color-paper);
    color: var(--color-ink);
    line-height: 1.7;
    font-size: 15px;
    overflow-x: hidden;
    -webkit-text-size-adjust: 100%;
}

.icon { width:15px; height:15px; display:block; flex-shrink:0; }
.toggle-icon svg { width:14px; height:14px; display:block; }

:focus-visible {
    outline: 2px solid var(--color-focus);
    outline-offset: 2px;
}

/* 헤더 */
.top-header {
    position: fixed; top:0; left:0; right:0; z-index: 100;
    background: var(--color-paper);
    border-bottom: 1px solid var(--color-rule);
    padding: 10px 24px;
    display: flex; align-items: center; gap: 12px;
}
.top-header h1 {
    font-family: var(--font-display);
    font-size: 17px; font-weight: 700;
    white-space: nowrap; font-style: normal;
}
.top-header .count { color: var(--color-ink-2); font-size: 12px; font-variant-numeric: tabular-nums; }

.search-box {
    flex: 1; max-width: 380px;
    position: relative;
}
.search-box input {
    width: 100%; padding: 7px 12px 7px 32px;
    border: 1px solid var(--color-rule); border-radius: 4px;
    background: var(--color-paper-2); color: var(--color-ink);
    font-family: var(--font-body);
    font-size: 14px; outline: none;
}
.search-box input:focus { border-color: var(--color-accent); }
.search-box input::placeholder { color: var(--color-ink-2); }
.search-box .icon {
    position: absolute; left: 9px; top: 50%;
    transform: translateY(-50%);
    color: var(--color-ink-2);
    pointer-events: none;
}

.header-actions { display: flex; gap: 6px; margin-left: auto; }
.btn {
    padding: 6px 12px; border-radius: 4px; border: 1px solid var(--color-rule);
    background: transparent; color: var(--color-ink); cursor: pointer;
    font-family: var(--font-body);
    font-size: 13px; white-space: nowrap;
    display: inline-flex; align-items: center; gap: 6px;
    text-decoration: none;
    transition: background-color var(--dur-short) var(--ease-out);
}
.btn:hover { background: var(--color-accent-wash); }

.icon-sun { display: none; }
[data-theme="dark"] .icon-sun { display: block; }
[data-theme="dark"] .icon-moon { display: none; }

/* 레이아웃 */
.layout {
    display: flex;
    max-width: 100%; overflow-x: hidden;
}

/* 사이드바 */
.sidebar {
    position: fixed; top: var(--header-h, 52px); left: 0; bottom: 0;
    width: 280px; background: var(--color-paper-3);
    border-right: 1px solid var(--color-rule);
    overflow-y: auto; padding: 12px 0;
    transition: transform var(--dur-med) var(--ease-out);
    z-index: 50;
}
.sidebar.hidden { transform: translateX(-100%); }

.sidebar ul { list-style: none; }
.sidebar li { border-bottom: 1px solid var(--color-rule); }
.toc-link {
    display: flex; align-items: baseline; gap: 8px;
    padding: 8px 16px; color: var(--color-ink); text-decoration: none;
    font-size: 13px; line-height: 1.4;
    transition: background-color var(--dur-short) var(--ease-out);
}
.toc-link:hover { background: var(--color-accent-wash); }
.toc-link.active { background: var(--color-accent-wash); color: var(--color-accent); font-weight: 600; }
.toc-num {
    color: var(--color-accent); font-size: 11px; min-width: 24px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
}

/* 메인 콘텐츠 */
.main {
    margin-left: 280px; flex: 1;
    padding: 20px 32px 80px; max-width: 880px;
}
.sidebar.hidden ~ .main { margin-left: 0; }

/* 섹션: Long Document 리듬 */
.section-card {
    border-top: 1px solid var(--color-rule);
    background: transparent;
}
.section-card:last-child { border-bottom: 1px solid var(--color-rule); }
.section-card.hidden { display: none; }
.section-card.highlight .section-title { color: var(--color-accent); }

.section-header {
    display: flex; align-items: baseline; gap: 14px;
    padding: 15px 4px; cursor: pointer;
    user-select: none;
}
.section-header:hover .section-title { color: var(--color-accent); }
.section-header:focus-visible { outline-offset: -2px; }
.section-num {
    color: var(--color-accent);
    font-size: 12px; font-weight: 600;
    min-width: 26px;
    font-variant-numeric: tabular-nums;
}
.section-title {
    flex:1;
    font-family: var(--font-display);
    font-size: 16.5px; font-weight: 600; line-height: 1.5;
    font-style: normal;
    transition: color var(--dur-short) var(--ease-out);
}
.toggle-icon {
    color: var(--color-ink-2);
    align-self: center;
    transition: transform var(--dur-short) var(--ease-out);
}
.section-card.collapsed .toggle-icon { transform: rotate(-90deg); }
.section-card.collapsed .section-body { display: none; }

.section-body { padding: 0 4px 24px 40px; max-width: 740px; }

/* 블록쿼트 */
.source-quote {
    border-left: 2px solid var(--quote-rule);
    background: var(--quote-bg);
    padding: 12px 16px;
    margin: 10px 0;
    font-size: 14px;
    color: var(--color-ink);
}
.quote-line { margin: 3px 0; }
.quote-line.indent { margin-left: 22px; font-size: 13px; }
.text-line.indent, .bold-line.indent { margin-left: 24px; }

/* 메모 (내 생각) */
.memo-item, .memo-bullet {
    padding: 4px 0 4px 8px;
    border-left: 2px solid var(--memo-rule);
    margin: 4px 0 4px 4px;
    background: var(--memo-bg);
    padding-left: 12px;
    font-size: 14px;
}
.memo-item.indent, .memo-bullet.indent {
    margin-left: 24px;
    border-left-color: var(--color-rule);
    background: transparent;
}
.memo-num { font-weight: 700; color: var(--color-accent); }

/* 3-Line Summary / 요약 */
.sub-summary {
    background: var(--summary-bg);
    border: 1px solid var(--summary-rule);
    padding: 10px 14px;
    margin: 10px 0;
}
.sub-summary h4 {
    font-size: 12px; color: var(--summary-head);
    margin-bottom: 6px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.5px;
    font-style: normal;
}

/* 기타 */
mark { background: var(--highlight-bg); color: var(--highlight-ink); padding: 0 2px; }
.wiki-link { color: var(--wiki-link); font-weight: 500; }
.note-image { margin: 14px 0; }
.note-image img {
    display: block;
    max-width: 100%;
    height: auto;
    border: 1px solid var(--color-rule);
    background: var(--color-paper-2);
}
.missing-image {
    margin: 10px 0;
    padding: 10px 12px;
    color: var(--missing-ink);
    background: var(--missing-bg);
    border: 1px solid var(--missing-rule);
    font-size: 13px;
}
.bold-line { font-weight: 700; margin: 6px 0; }
.text-line { margin: 2px 0; }
.data-table {
    width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 13px;
    font-variant-numeric: tabular-nums;
}
.data-table td {
    border: 1px solid var(--color-rule); padding: 6px 10px;
}
.data-table tr:first-child td { font-weight: 700; background: var(--color-paper-3); }

h4 { font-size: 14px; margin: 12px 0 6px; color: var(--color-accent); font-style: normal; }

/* 검색 하이라이트 */
.search-highlight { background: var(--search-hl-bg); color: var(--search-hl-ink); padding: 0 1px; }

/* 스크롤 투 탑 */
.scroll-top {
    position: fixed; bottom: 24px; right: 24px;
    width: 38px; height: 38px; border-radius: 4px;
    background: var(--color-paper-2); color: var(--color-ink);
    display: flex; align-items: center; justify-content: center;
    cursor: pointer; border: 1px solid var(--color-rule);
    box-shadow: var(--shadow);
    opacity: 0; pointer-events: none;
    transition: opacity var(--dur-med) var(--ease-out);
}
.scroll-top.visible { opacity: 1; pointer-events: auto; }
.scroll-bottom { bottom: 70px; }

/* 모바일 */
@media (max-width: 768px) {
    .top-header { padding: 8px 10px; gap: 6px; flex-wrap: wrap; }
    .top-header h1 { font-size: 14px; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
    .top-header .count { display: none; }
    .search-box { order: 10; flex: 1 1 100%; max-width: 100%; }
    .header-actions { gap: 4px; }
    .header-actions .btn { padding: 5px 7px; font-size: 11px; }
    .sidebar {
        width: min(280px, 85vw); transform: translateX(-100%);
        box-shadow: 2px 0 12px oklch(0% 0 0 / 0.15);
    }
    .sidebar.visible { transform: translateX(0); }
    .main {
        margin-left: 0 !important; padding: 10px 10px 60px;
        max-width: 100%; width: 100%; overflow-x: hidden;
    }
    .section-header { padding: 12px 2px; gap: 8px; }
    .section-title { font-size: 14.5px; word-break: keep-all; overflow-wrap: break-word; }
    .section-body { padding: 0 2px 18px; overflow-x: auto; word-break: keep-all; overflow-wrap: break-word; }
    .source-quote { padding: 10px 12px; font-size: 13px; }
    .quote-line { word-break: keep-all; overflow-wrap: break-word; }
    .memo-item, .memo-bullet { font-size: 13px; }
    .data-table { font-size: 12px; display: block; overflow-x: auto; }
    .sidebar-overlay {
        display: none; position: fixed; inset: 0; top: var(--header-h, 52px);
        background: oklch(0% 0 0 / 0.4); z-index: 40;
    }
    .sidebar-overlay.visible { display: block; }
}

@media (prefers-reduced-motion: reduce) {
    * { transition-duration: 0.01ms !important; animation: none !important; }
}
</style>
</head>
<body>

<div class="top-header">
    <a href="/" class="btn" aria-label="홈"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 10.8 12 3.5l9 7.3"/><path d="M5.5 9.5V20a.8.8 0 0 0 .8.8h11.4a.8.8 0 0 0 .8-.8V9.5"/></svg></a>
    <a href="https://weekly-input.vercel.app/" class="btn" title="주기적 인풋 정리" aria-label="주기적 인풋 정리"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.5 4h17v4h-17z"/><path d="M5 8v11.2a.8.8 0 0 0 .8.8h12.4a.8.8 0 0 0 .8-.8V8"/><path d="M10 12h4"/></svg></a>
    <button class="btn" onclick="toggleSidebar()" id="sidebarBtn" aria-label="목차 열기/닫기"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg></button>
    <h1>{{TITLE}}</h1>
    <span class="count">{{COUNT}}개 섹션</span>
    <div class="search-box">
        <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.4-4.4"/></svg>
        <input type="text" id="searchInput" placeholder="검색어 입력... (제목 + 본문)" oninput="handleSearch(this.value)">
    </div>
    <div class="header-actions">
        <button class="btn" onclick="expandAll()">전체 펼치기</button>
        <button class="btn" onclick="collapseAll()">전체 접기</button>
        <button class="btn" onclick="toggleTheme()" id="themeBtn" aria-label="테마 전환"><svg class="icon icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 13.2A8 8 0 1 1 10.8 4a6.5 6.5 0 0 0 9.2 9.2z"/></svg><svg class="icon icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.8V5M12 19v2.2M2.8 12H5M19 12h2.2M5.2 5.2l1.6 1.6M17.2 17.2l1.6 1.6M18.8 5.2l-1.6 1.6M6.8 17.2l-1.6 1.6"/></svg></button>
    </div>
</div>

<div class="sidebar-overlay" id="sidebarOverlay" onclick="closeSidebar()"></div>
<div class="layout">
    <nav class="sidebar" id="sidebar">
        <ul id="tocList">
            {{TOC}}
        </ul>
    </nav>
    <main class="main" id="mainContent">
        {{SECTIONS}}
    </main>
</div>

<button class="scroll-top" id="scrollTop" onclick="window.scrollTo({top:0,behavior:'smooth'})" aria-label="맨 위로"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 19V5"/><path d="M5.5 11.5 12 5l6.5 6.5"/></svg></button>
<button class="scroll-top scroll-bottom" id="scrollBottom" onclick="window.scrollTo({top:document.body.scrollHeight,behavior:'smooth'})" aria-label="맨 아래로"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5v14"/><path d="M5.5 12.5 12 19l6.5-6.5"/></svg></button>

<script>
// 테마
function toggleTheme() {
    const html = document.documentElement;
    const isDark = html.getAttribute('data-theme') === 'dark';
    html.setAttribute('data-theme', isDark ? 'light' : 'dark');
    localStorage.setItem('theme', isDark ? 'light' : 'dark');
}
(function() {
    const saved = localStorage.getItem('theme');
    if (saved === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
    }
})();

// 헤더 높이 동적 측정
function syncHeaderHeight() {
    const h = document.querySelector('.top-header').offsetHeight;
    document.documentElement.style.setProperty('--header-h', h + 'px');
    document.querySelector('.layout').style.marginTop = h + 'px';
}
syncHeaderHeight();
window.addEventListener('resize', syncHeaderHeight);

// 사이드바
function isMobile() { return window.innerWidth <= 768; }
function toggleSidebar() {
    const sb = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    if (isMobile()) {
        sb.classList.toggle('visible');
        overlay.classList.toggle('visible');
    } else {
        const main = document.getElementById('mainContent');
        sb.classList.toggle('hidden');
        main.style.marginLeft = sb.classList.contains('hidden') ? '0' : '280px';
    }
}
function closeSidebar() {
    document.getElementById('sidebar').classList.remove('visible');
    document.getElementById('sidebarOverlay').classList.remove('visible');
}
document.getElementById('sidebar').addEventListener('click', function(e) {
    if (e.target.closest('a') && isMobile()) closeSidebar();
});

// 섹션 접기/펼치기
function toggleSection(header) {
    header.parentElement.classList.toggle('collapsed');
}
function expandAll() {
    document.querySelectorAll('.section-card').forEach(c => c.classList.remove('collapsed'));
}
function collapseAll() {
    document.querySelectorAll('.section-card').forEach(c => c.classList.add('collapsed'));
}

// 검색
let searchTimeout;
function handleSearch(query) {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => doSearch(query), 200);
}
function doSearch(query) {
    const cards = document.querySelectorAll('.section-card');
    const tocLinks = document.querySelectorAll('.toc-link');
    const q = query.trim().toLowerCase();

    // 이전 하이라이트 제거
    document.querySelectorAll('.search-highlight').forEach(el => {
        el.replaceWith(el.textContent);
    });

    if (!q) {
        cards.forEach(c => { c.classList.remove('hidden'); c.classList.remove('highlight'); });
        tocLinks.forEach(l => l.parentElement.style.display = '');
        return;
    }

    cards.forEach((card, i) => {
        const text = card.textContent.toLowerCase();
        const match = text.includes(q);
        card.classList.toggle('hidden', !match);
        card.classList.toggle('highlight', match);
        tocLinks[i].parentElement.style.display = match ? '' : 'none';
        if (match) {
            card.classList.remove('collapsed');
        }
    });
}

// TOC 활성화 (스크롤)
const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            const idx = entry.target.dataset.index;
            document.querySelectorAll('.toc-link').forEach(l => l.classList.remove('active'));
            const active = document.querySelector(`.toc-link[data-index="${idx}"]`);
            if (active) {
                active.classList.add('active');
                active.scrollIntoView({ block: 'nearest' });
            }
        }
    });
}, { threshold: 0.1, rootMargin: '-60px 0px -60% 0px' });

document.querySelectorAll('.section-card').forEach(c => observer.observe(c));

// 스크롤 투 탑 / 바텀
function updateScrollBtns() {
    document.getElementById('scrollTop').classList.toggle('visible', window.scrollY > 400);
    const nearBottom = window.scrollY + window.innerHeight >= document.body.scrollHeight - 400;
    document.getElementById('scrollBottom').classList.toggle('visible', !nearBottom);
}
window.addEventListener('scroll', updateScrollBtns);
window.addEventListener('resize', updateScrollBtns);
updateScrollBtns();

// 기본 접기
document.addEventListener('DOMContentLoaded', () => {
    // 처음에 전체 펼침 상태로 시작
});
</script>

</body>
</html>'''


def main():
    global IMAGE_URLS

    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"G:\내 드라이브\default vaultrealrealreal\30. PROJECT (현재 진행 프로젝트)\33. 생활사 (투자, 개인 블로그 등)\주식 스터디\학습 모음\2026년 상반기 학습 모음~6월 말까지.md")
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(r"D:\code_project\md2html\2026_학습모음.html")

    print(f"Reading: {src}")
    md_text = src.read_text(encoding='utf-8')
    print(f"  {len(md_text):,} chars, {md_text.count(chr(10)):,} lines")

    IMAGE_URLS = prepare_images(md_text, src, dst.parent)

    sections = parse_sections(md_text)
    print(f"  {len(sections)} sections parsed")

    title = make_title(src)
    print(f"  title: {title}")

    html_out = generate_html(sections, title)
    dst.write_text(html_out, encoding='utf-8')
    print(f"Output: {dst}")
    print(f"  {len(html_out):,} chars")


if __name__ == '__main__':
    main()
