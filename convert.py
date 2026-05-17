"""
Markdown 학습 노트 → HTML 대시보드 변환기
- 사이드바 TOC + 검색 + 접이식 섹션 + 다크모드
- 3-Line Summary / 요약은 상위 섹션에 종속
"""

import re
import html
import sys
from pathlib import Path


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

        # 본문 처리
        if current:
            current['body'] += process_line(stripped) + '\n'

        i += 1

    if current:
        if in_sub:
            current['body'] += '</div>\n'
        sections.append(current)

    return sections


def is_sub_section(title: str) -> bool:
    t = title.lower().strip().strip('*').strip()
    return any(k in t for k in ['3-line summary', '3 line summary', '요약'])


def clean_title(title: str) -> str:
    """Obsidian [[]] 링크, ** 등 정리"""
    title = re.sub(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]', lambda m: m.group(2) or m.group(1), title)
    title = title.replace('**', '').replace('****', '').strip()
    # 이모지는 유지
    return title


def process_line(line: str) -> str:
    """한 줄을 HTML로 변환"""
    if not line:
        return '<br>'

    # 블록쿼트
    if line.startswith('>'):
        content = line.lstrip('>').strip()
        # 중첩 블록쿼트 제거 후 처리
        content = inline_format(html.escape(content))
        return f'<div class="quote-line">{content}</div>'

    # 순서 리스트
    ol_match = re.match(r'^(\d+)\.\s+(.+)', line)
    if ol_match:
        content = inline_format(html.escape(ol_match.group(2)))
        return f'<div class="memo-item"><span class="memo-num">{ol_match.group(1)}.</span> {content}</div>'

    # 비순서 리스트
    ul_match = re.match(r'^[-*]\s+(.+)', line)
    if ul_match:
        content = inline_format(html.escape(ul_match.group(1)))
        return f'<div class="memo-bullet">• {content}</div>'

    # 들여쓴 리스트
    indent_match = re.match(r'^(\t+|\s{2,})(\d+)\.\s+(.+)', line)
    if indent_match:
        content = inline_format(html.escape(indent_match.group(3)))
        return f'<div class="memo-item indent">{indent_match.group(2)}. {content}</div>'

    indent_ul_match = re.match(r'^(\t+|\s{2,})[-*]\s+(.+)', line)
    if indent_ul_match:
        content = inline_format(html.escape(indent_ul_match.group(2)))
        return f'<div class="memo-bullet indent">• {content}</div>'

    # 테이블 (간단 처리)
    if '|' in line and line.startswith('|'):
        cells = [c.strip() for c in line.split('|')[1:-1]]
        if all(re.match(r'^[-:]+$', c) for c in cells):
            return ''  # 구분선 스킵
        row = ''.join(f'<td>{inline_format(html.escape(c))}</td>' for c in cells)
        return f'<tr>{row}</tr>'

    # 볼드 텍스트 라인
    if line.startswith('**') and line.endswith('**'):
        content = inline_format(html.escape(line.strip('*').strip()))
        return f'<div class="bold-line">{content}</div>'

    # 일반 텍스트
    content = inline_format(html.escape(line))
    return f'<div class="text-line">{content}</div>'


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


def generate_html(sections: list[dict]) -> str:
    """섹션 리스트를 HTML 대시보드로 변환"""

    # TOC 생성
    toc_items = []
    for i, sec in enumerate(sections):
        title_short = sec['title'][:40] + ('...' if len(sec['title']) > 40 else '')
        toc_items.append(
            f'<li><a href="#{sec["id"]}" class="toc-link" data-index="{i}">'
            f'<span class="toc-num">{i+1}</span>{html.escape(title_short)}</a></li>'
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
            <div class="section-header" onclick="toggleSection(this)">
                <span class="section-num">{i+1}</span>
                <h2 class="section-title">{html.escape(sec['title'])}</h2>
                <span class="toggle-icon">▼</span>
            </div>
            <div class="section-body">
                {body}
            </div>
        </div>''')
    sections_html = '\n'.join(section_cards)

    return HTML_TEMPLATE.replace('{{TOC}}', toc_html).replace('{{SECTIONS}}', sections_html).replace('{{COUNT}}', str(len(sections)))


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
<html lang="ko" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>2026년 학습 모음</title>
<style>
:root {
    --bg: #f5f5f0;
    --bg-card: #ffffff;
    --bg-sidebar: #fafaf7;
    --text: #1a1a1a;
    --text-sub: #666;
    --border: #e0ddd5;
    --accent: #2563eb;
    --accent-light: #dbeafe;
    --quote-bg: #f8f7f4;
    --quote-border: #c9c4b8;
    --memo-bg: #fef9e7;
    --memo-border: #f0c040;
    --highlight: #fef08a;
    --summary-bg: #f0fdf4;
    --summary-border: #86efac;
    --wiki-link: #7c3aed;
    --shadow: 0 1px 3px rgba(0,0,0,0.08);
    --header-bg: #ffffff;
}
[data-theme="dark"] {
    --bg: #0f0f0f;
    --bg-card: #1a1a1a;
    --bg-sidebar: #141414;
    --text: #e5e5e5;
    --text-sub: #999;
    --border: #2a2a2a;
    --accent: #60a5fa;
    --accent-light: #1e3a5f;
    --quote-bg: #1e1e1a;
    --quote-border: #555040;
    --memo-bg: #2a2510;
    --memo-border: #b8942e;
    --highlight: #854d0e;
    --summary-bg: #0a200f;
    --summary-border: #22c55e;
    --wiki-link: #a78bfa;
    --shadow: 0 1px 3px rgba(0,0,0,0.3);
    --header-bg: #1a1a1a;
}

* { margin:0; padding:0; box-sizing:border-box; }

body {
    font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.7;
    font-size: 15px;
    overflow-x: hidden;
    -webkit-text-size-adjust: 100%;
}

/* 헤더 */
.top-header {
    position: fixed; top:0; left:0; right:0; z-index: 100;
    background: var(--header-bg);
    border-bottom: 1px solid var(--border);
    padding: 10px 24px;
    display: flex; align-items: center; gap: 16px;
    backdrop-filter: blur(10px);
}
.top-header h1 { font-size: 18px; font-weight: 700; white-space: nowrap; }
.top-header .count { color: var(--text-sub); font-size: 13px; }

.search-box {
    flex: 1; max-width: 400px;
    position: relative;
}
.search-box input {
    width: 100%; padding: 8px 12px 8px 36px;
    border: 1px solid var(--border); border-radius: 8px;
    background: var(--bg); color: var(--text);
    font-size: 14px; outline: none;
}
.search-box input:focus { border-color: var(--accent); }
.search-box::before {
    content: '🔍'; position: absolute; left: 10px; top: 50%;
    transform: translateY(-50%); font-size: 14px;
}

.header-actions { display: flex; gap: 8px; margin-left: auto; }
.btn {
    padding: 6px 14px; border-radius: 6px; border: 1px solid var(--border);
    background: var(--bg-card); color: var(--text); cursor: pointer;
    font-size: 13px; white-space: nowrap;
}
.btn:hover { border-color: var(--accent); }

/* 레이아웃 */
.layout {
    display: flex;
    max-width: 100%; overflow-x: hidden;
}

/* 사이드바 */
.sidebar {
    position: fixed; top: var(--header-h, 52px); left: 0; bottom: 0;
    width: 280px; background: var(--bg-sidebar);
    border-right: 1px solid var(--border);
    overflow-y: auto; padding: 12px 0;
    transition: transform 0.3s;
    z-index: 50;
}
.sidebar.hidden { transform: translateX(-100%); }

.sidebar ul { list-style: none; }
.sidebar li { border-bottom: 1px solid var(--border); }
.toc-link {
    display: flex; align-items: baseline; gap: 8px;
    padding: 8px 16px; color: var(--text); text-decoration: none;
    font-size: 13px; line-height: 1.4;
    transition: background 0.15s;
}
.toc-link:hover { background: var(--accent-light); }
.toc-link.active { background: var(--accent-light); color: var(--accent); font-weight: 600; }
.toc-num {
    color: var(--text-sub); font-size: 11px; min-width: 24px;
    font-variant-numeric: tabular-nums;
}

/* 메인 콘텐츠 */
.main {
    margin-left: 280px; flex: 1;
    padding: 20px 24px 60px; max-width: 860px;
}
.sidebar.hidden ~ .main { margin-left: 0; }

/* 섹션 카드 */
.section-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 10px;
    margin-bottom: 12px;
    box-shadow: var(--shadow);
    overflow: hidden;
    transition: box-shadow 0.2s;
}
.section-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.12); }
.section-card.hidden { display: none; }
.section-card.highlight { border-color: var(--accent); }

.section-header {
    display: flex; align-items: center; gap: 10px;
    padding: 14px 18px; cursor: pointer;
    user-select: none;
}
.section-header:hover { background: var(--accent-light); }
.section-num {
    background: var(--accent); color: #fff;
    font-size: 11px; font-weight: 700;
    min-width: 28px; height: 22px;
    display: flex; align-items: center; justify-content: center;
    border-radius: 4px;
}
.section-title { flex:1; font-size: 15px; font-weight: 600; }
.toggle-icon {
    font-size: 12px; color: var(--text-sub);
    transition: transform 0.2s;
}
.section-card.collapsed .toggle-icon { transform: rotate(-90deg); }
.section-card.collapsed .section-body { display: none; }

.section-body { padding: 0 18px 16px; }

/* 블록쿼트 */
.source-quote {
    border-left: 3px solid var(--quote-border);
    background: var(--quote-bg);
    padding: 12px 16px;
    margin: 10px 0;
    border-radius: 0 6px 6px 0;
    font-size: 14px;
    color: var(--text);
}
.quote-line { margin: 3px 0; }

/* 메모 (내 생각) */
.memo-item, .memo-bullet {
    padding: 4px 0 4px 8px;
    border-left: 3px solid var(--memo-border);
    margin: 4px 0 4px 4px;
    background: var(--memo-bg);
    border-radius: 0 4px 4px 0;
    padding-left: 12px;
    font-size: 14px;
}
.memo-item.indent, .memo-bullet.indent {
    margin-left: 24px;
    border-left-color: #ddd;
    background: transparent;
}
.memo-num { font-weight: 700; color: var(--accent); }

/* 3-Line Summary / 요약 */
.sub-summary {
    background: var(--summary-bg);
    border: 1px solid var(--summary-border);
    border-radius: 6px;
    padding: 10px 14px;
    margin: 10px 0;
}
.sub-summary h4 {
    font-size: 13px; color: var(--summary-border);
    margin-bottom: 6px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.5px;
}

/* 기타 */
mark { background: var(--highlight); padding: 0 2px; border-radius: 2px; }
.wiki-link { color: var(--wiki-link); font-weight: 500; }
.bold-line { font-weight: 700; margin: 6px 0; }
.text-line { margin: 2px 0; }
.data-table {
    width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 13px;
}
.data-table td {
    border: 1px solid var(--border); padding: 6px 10px;
}
.data-table tr:first-child td { font-weight: 700; background: var(--bg); }

h4 { font-size: 14px; margin: 12px 0 6px; color: var(--accent); }

/* 검색 하이라이트 */
.search-highlight { background: #fbbf24; color: #000; padding: 0 1px; border-radius: 2px; }

/* 스크롤 투 탑 */
.scroll-top {
    position: fixed; bottom: 24px; right: 24px;
    width: 40px; height: 40px; border-radius: 50%;
    background: var(--accent); color: #fff;
    display: flex; align-items: center; justify-content: center;
    cursor: pointer; font-size: 18px; border: none;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    opacity: 0; transition: opacity 0.3s;
}
.scroll-top.visible { opacity: 1; }

/* 모바일 */
@media (max-width: 768px) {
    .top-header { padding: 8px 10px; gap: 6px; flex-wrap: wrap; }
    .top-header h1 { font-size: 14px; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
    .top-header .count { display: none; }
    .search-box { order: 10; flex: 1 1 100%; max-width: 100%; }
    .header-actions { gap: 4px; }
    .header-actions .btn { padding: 4px 6px; font-size: 11px; }
    .sidebar {
        width: min(280px, 85vw); transform: translateX(-100%);
        box-shadow: 2px 0 12px rgba(0,0,0,0.15);
    }
    .sidebar.visible { transform: translateX(0); }
    .main {
        margin-left: 0 !important; padding: 10px 8px;
        max-width: 100vw; width: 100%; overflow-x: hidden;
    }
    .section-card { border-radius: 8px; }
    .section-header { padding: 10px 12px; gap: 8px; }
    .section-title { font-size: 14px; word-break: keep-all; overflow-wrap: break-word; }
    .section-body { padding: 0 12px 12px; overflow-x: auto; word-break: keep-all; overflow-wrap: break-word; }
    .source-quote { padding: 10px 12px; font-size: 13px; }
    .quote-line { word-break: keep-all; overflow-wrap: break-word; }
    .memo-item, .memo-bullet { font-size: 13px; }
    .data-table { font-size: 12px; display: block; overflow-x: auto; }
    .sidebar-overlay {
        display: none; position: fixed; inset: 0; top: var(--header-h, 52px);
        background: rgba(0,0,0,0.4); z-index: 40;
    }
    .sidebar-overlay.visible { display: block; }
}
</style>
</head>
<body>

<div class="top-header">
    <button class="btn" onclick="toggleSidebar()" id="sidebarBtn">☰</button>
    <h1>2026년 학습 모음</h1>
    <span class="count">{{COUNT}}개 섹션</span>
    <div class="search-box">
        <input type="text" id="searchInput" placeholder="검색어 입력... (제목 + 본문)" oninput="handleSearch(this.value)">
    </div>
    <div class="header-actions">
        <button class="btn" onclick="expandAll()">전체 펼치기</button>
        <button class="btn" onclick="collapseAll()">전체 접기</button>
        <button class="btn" onclick="toggleTheme()" id="themeBtn">🌙 다크</button>
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

<button class="scroll-top" id="scrollTop" onclick="window.scrollTo({top:0,behavior:'smooth'})">↑</button>

<script>
// 테마
function toggleTheme() {
    const html = document.documentElement;
    const isDark = html.getAttribute('data-theme') === 'dark';
    html.setAttribute('data-theme', isDark ? 'light' : 'dark');
    document.getElementById('themeBtn').textContent = isDark ? '🌙 다크' : '☀️ 라이트';
    localStorage.setItem('theme', isDark ? 'light' : 'dark');
}
(function() {
    const saved = localStorage.getItem('theme');
    if (saved === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
        document.addEventListener('DOMContentLoaded', () => {
            document.getElementById('themeBtn').textContent = '☀️ 라이트';
        });
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

// 스크롤 투 탑
window.addEventListener('scroll', () => {
    document.getElementById('scrollTop').classList.toggle('visible', window.scrollY > 400);
});

// 기본 접기
document.addEventListener('DOMContentLoaded', () => {
    // 처음에 전체 펼침 상태로 시작
});
</script>

</body>
</html>'''


def main():
    src = Path(r"G:\내 드라이브\default vaultrealrealreal\30. PROJECT (현재 진행 프로젝트)\33. 생활사 (투자, 개인 블로그 등)\주식 스터디\학습 모음\2026년 학습 모음.md")
    dst = Path(r"D:\code_project\md2html\2026_학습모음.html")

    print(f"Reading: {src}")
    md_text = src.read_text(encoding='utf-8')
    print(f"  {len(md_text):,} chars, {md_text.count(chr(10)):,} lines")

    sections = parse_sections(md_text)
    print(f"  {len(sections)} sections parsed")

    html_out = generate_html(sections)
    dst.write_text(html_out, encoding='utf-8')
    print(f"Output: {dst}")
    print(f"  {len(html_out):,} chars")


if __name__ == '__main__':
    main()
