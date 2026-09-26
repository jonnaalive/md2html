# 학습 모음 md -> html 재생성 후 Vercel 배포
# 사용법: pwsh D:\code_project\md2html\deploy.ps1
$ErrorActionPreference = 'Stop'

$root  = 'D:\code_project\md2html'
$vault = 'G:\내 드라이브\default vaultrealrealreal\30. PROJECT (현재 진행 프로젝트)\33. 생활사 (투자, 개인 블로그 등)\주식 스터디\학습 모음'

python "$root\convert.py" "$vault\2026년 상반기 학습 모음~6월 말까지.md" "$root\2026_학습모음.html"
python "$root\convert.py" "$vault\2026년 하반기 학습 모음.md" "$root\2026_하반기_학습모음.html"

vercel --prod --yes --cwd $root
