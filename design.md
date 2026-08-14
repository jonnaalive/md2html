# Design — md2html 학습 노트 아카이브

이 앱의 잠긴 디자인 시스템. 페이지를 다시 디자인하기 전에 반드시 이 파일을 먼저 읽는다.
페이지별로 시스템을 새로 만들지 말 것. 시스템이 자라야 하면 이 파일을 수정한다.

## Genre
editorial

## Macrostructure family
- Content pages (노트 페이지, convert.py 템플릿): **Long Document** : 순번 있는 섹션이 헤어라인 룰로 구분되는 문서 리듬. 섹션 번호는 실제 순번이므로 넘버링 허용.
- Hub page (index.html): **Catalogue index** : 마스트헤드 + 번호 달린 목차 리스트.

## Theme (custom · light / dark 쌍)
라이트:
- `--color-paper`   oklch(96.5% 0.012 90)  : 웜 페이퍼
- `--color-paper-2` oklch(98.5% 0.006 90)  : 인풋/이미지 배경
- `--color-paper-3` oklch(94% 0.014 88)    : 사이드바/워시
- `--color-ink`     oklch(24% 0.012 60)
- `--color-ink-2`   oklch(47% 0.014 60)
- `--color-rule`    oklch(87% 0.012 85)
- `--color-accent`  oklch(52% 0.15 35)     : 진한 주홍, 페이지당 유일한 UI 액센트
- `--color-focus`   = accent

다크 (`[data-theme="dark"]`, index는 `prefers-color-scheme`):
- paper oklch(22% 0.012 60) 계열로 전 토큰 재정의. 순흑 금지.

시맨틱 토큰(quote/memo/summary/highlight/missing)은 기능적 색 구분이므로 유지하되
저채도로 페이퍼에 조화시킨다. 값은 convert.py 템플릿 토큰 블록이 정본.

## Typography
- Display: Noto Serif KR, weight 600–700, style normal (제목·마스트헤드·섹션 타이틀)
- Body: Pretendard Variable (jsdelivr dynamic-subset), weight 400–700
- 숫자 컬럼·순번: `font-variant-numeric: tabular-nums`, 2자리 제로 패딩 (01, 02…)
- 이탤릭 헤더 금지. 강조는 weight 또는 액센트 색으로.

## Spacing
4pt 기반. 섹션 패딩은 헤어라인 룰 리듬에 맞춰 15px 내외, 본문 measure 최대 740px.

## Motion
- `--ease-out: cubic-bezier(0.16, 1, 0.3, 1)` · `--dur-short: 160ms` · `--dur-med: 250ms`
- `transition-all` 금지, 속성 명시. hover 신호는 요소당 1개 (색 변화).
- 포커스 링은 즉시 표시 (트랜지션 금지). `prefers-reduced-motion` 대응 필수.

## Microinteractions stance
- 사일런트 석세스. 토스트·축하 애니메이션 없음.
- 아이콘은 인라인 SVG, stroke 1.5px, currentColor. 이모지 아이콘 금지.

## What pages MUST share
- 페이퍼·잉크·룰·액센트 토큰과 폰트 페어링
- 번호(tabular-nums, 액센트 색) + 세리프 제목의 행 리듬
- 헤어라인 룰 구분 언어 (박스·그림자 최소화)

## What pages MAY differ on
- family 안에서의 매크로 구조 (노트 페이지 vs 허브 페이지)
- 노트 페이지의 시맨틱 블록(인용/메모/요약) 구성

## Per-page allowances
- 전 페이지 enrichment 없음. 타이포그래피 온리.

## Exports

### tokens.css
`tokens.css` 파일 참조 (라이트/다크 전체 토큰). 페이지는 자급자족(임베드)이며
tokens.css는 다른 프로젝트로 시스템을 옮길 때 쓰는 포터블 사본이다.
