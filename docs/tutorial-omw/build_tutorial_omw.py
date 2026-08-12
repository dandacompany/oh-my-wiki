#!/usr/bin/env python3
"""Self-contained static HTML tutorial builder for the current oh-my-wiki release.

Single-file: HEAD (full <head> + <style>), esc(), render_section(), SECTIONS, body(), main().
Command examples are kept in sync with the current public CLI contract.
Personal OMW_HOME paths are shown as ~/.omw.
"""
import html
import pathlib
import re
import sys

BASE = pathlib.Path(__file__).resolve().parent
OUT = BASE / "tutorial-omw.html"
ROOT = BASE.parent.parent
sys.path.insert(0, str(ROOT))

from scripts.ops_registry import OPS  # noqa: E402


def _project_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise RuntimeError("project version not found in pyproject.toml")
    return match.group(1)


VERSION = _project_version()
CLI_OPS = tuple(op for op in OPS if op.kind == "deterministic")
SKILL_OPS = tuple(op for op in OPS if op.kind == "procedure")
CLI_COUNT = len(CLI_OPS)
SKILL_COUNT = len(SKILL_OPS)

OP_SUMMARY_KO = {
    "status": "레지스트리와 활성 vault 상태를 JSON으로 표시",
    "vault": "vault 생성·전환·이름 변경·이동·보관·삭제",
    "lint": "vault의 문서·링크·구조 문제 검사",
    "reindex": "파일을 다시 읽어 검색·그래프 색인 갱신",
    "connections": "그래프의 주제 묶음·다리·중심 페이지 확인",
    "fields": "페이지의 frontmatter와 인라인 필드 표시",
    "links": "연결할 엔티티를 제안하고 링크 삽입",
    "review": "다시 검토할 페이지와 검토 결과 관리",
    "supersede": "오래된 페이지를 새 페이지로 대체 표시",
    "merge": "두 페이지를 제안 파일을 거쳐 하나로 통합",
    "visibility": "페이지의 공개·비공개 상태 조회·설정",
    "inbox": "URL 받은함 추가·조회·수집·재시도",
    "fetch": "URL 하나를 LLM 없이 raw에 저장",
    "schema": "페이지 타입 규약 목록·상세 표시",
    "search": "설정된 공급자로 웹 검색",
    "serve": "읽기 전용 로컬 검색 HTTP API 실행",
    "view": "vault·페이지·검색을 Obsidian/Logseq에서 열기",
    "recall": "에이전트 훅에서 사용할 위키 회상 실행",
    "candidates": "완료 세션의 지식 후보를 검토·승인·폐기",
    "maint": "자동화에 적합한 유지보수 상태 확인",
    "gate": "작업 종료 시 유지보수 필요 여부 기록·확인",
    "setup": "vault와 호스트 연결을 설정하는 마법사",
    "import": "폴더·Obsidian·Notion 자료 가져오기",
    "doctor": "설치·설정·경로 상태 진단",
    "update": "설치 방식에 맞춰 OMW 업데이트",
    "uninstall": "호스트 연결·설정·vault 제거",
    "next": "현재 상태에 맞는 다음 지식 작업 추천",
    "list": "태그·타입·상태 등으로 페이지 목록 필터링",
    "context": "본문과 인용 정보를 포함한 근거 검색",
    "embed": "로컬 임베딩 모델 설치·전환·재색인",
    "find": "vault 검색 색인에서 문서 찾기",
    "export": "선택한 페이지를 Markdown 폴더·zip으로 내보내기",
    "help": "모든 명령을 지식 흐름별로 안내",
    "version": "설치된 OMW 버전 표시",
    "report": "vault 통계와 건강 상태를 한 화면에 표시",
    "history": "과거 요청·결과·수정 주안점 기록·검색",
    "persona-run": "유지보수 페르소나 하나 실행",
    "persona-bundle": "이름 붙은 페르소나 묶음을 순서대로 실행",
    "persona-fanout": "여러 페이지용 페르소나 실행 명령 생성",
    "star": "GitHub 저장소 별표 상태 관리",
}

# ─────────────────────────────────────────────────────────────────────────────
# HEAD — full <head> + <style> (sand / stone / moss earth palette)
# ─────────────────────────────────────────────────────────────────────────────
HEAD = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>oh-my-wiki __VERSION__ — 따라 하는 위키 셋업</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;700;900&family=Noto+Sans+KR:wght@300;400;500;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{
  --sand:#d4c4a8;
  --stone-100:#f5f3ee; --stone-200:#e8e3d9;
  --stone-400:#a89876; --stone-500:#8a7a58;
  --stone-700:#5a4e38; --stone-800:#3e3526;
  --stone-900:#1f1a10;
  --moss:#6b7d4f; --cream:#fafaf7;
  --code-bg-a:#13171b; --code-bg-b:#0e1114;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
html,body{max-width:100%;overflow-x:hidden}
body{
  font-family:'Noto Sans KR',sans-serif;
  font-weight:400; font-size:15.5px; line-height:1.8;
  color:var(--stone-800);
  background:var(--stone-100);
  -webkit-font-smoothing:antialiased;
}
a{color:var(--moss);text-decoration:none;border-bottom:1px solid rgba(107,125,79,.35)}
a:hover{border-bottom-color:var(--moss)}
.container{max-width:880px;margin:0 auto;padding:0 28px}
code{font-family:'JetBrains Mono',monospace;font-size:.92em;
  background:var(--stone-200);color:var(--stone-700);
  padding:1px 6px;border-radius:4px}

/* ── hero ── */
.hero{
  background:
    linear-gradient(180deg, var(--stone-200) 0%, var(--stone-100) 100%);
  border-bottom:1px solid var(--stone-200);
  padding:78px 0 56px;
}
.hero-inner{max-width:880px;margin:0 auto;padding:0 28px}
.hero-badge{
  display:inline-block;font-family:'JetBrains Mono',monospace;font-weight:500;
  font-size:11.5px;letter-spacing:.4px;text-transform:uppercase;
  color:var(--stone-500);background:var(--cream);
  border:1px solid var(--sand);border-radius:999px;
  padding:5px 13px;margin-bottom:22px;
}
.hero h1{
  font-family:'Noto Serif KR',serif;font-weight:900;
  font-size:clamp(34px,5vw,48px);line-height:1.18;
  color:var(--stone-900);letter-spacing:-.5px;
}
.hero .tagline{
  margin-top:18px;font-size:16px;line-height:1.8;color:var(--stone-700);
  max-width:640px;
}
.meta-grid{
  margin-top:34px;display:grid;
  grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:0;
  border:1px solid var(--stone-200);border-radius:8px;overflow:hidden;
  background:var(--cream);
}
.meta-grid div{padding:14px 18px;border-right:1px solid var(--stone-200);border-bottom:1px solid var(--stone-200)}
.meta-grid dt{
  font-family:'JetBrains Mono',monospace;font-weight:500;
  font-size:11px;letter-spacing:.4px;text-transform:uppercase;color:var(--stone-400);
}
.meta-grid dd{margin-top:5px;font-size:14px;color:var(--stone-800);font-weight:500}

/* ── top nav / TOC ── */
nav.toc{
  position:sticky;top:0;z-index:20;
  background:rgba(245,243,238,.94);backdrop-filter:saturate(120%);
  border-bottom:1px solid var(--stone-200);
}
nav.toc .toc-inner{
  max-width:880px;margin:0 auto;padding:11px 28px;
  display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;
}
nav.toc a{
  font-family:'JetBrains Mono',monospace;font-weight:500;
  font-size:11px;letter-spacing:.3px;text-transform:uppercase;
  color:var(--stone-500);border-bottom:none;
}
nav.toc a:hover{color:var(--moss)}
nav.toc .tag{color:var(--stone-400);font-weight:700;margin-right:4px}

/* ── overview ── */
#overview{padding:60px 0 8px}
#overview .lede{font-size:16.5px;line-height:1.85;color:var(--stone-700);max-width:680px}

/* ── section rhythm ── */
section{padding:68px 0;border-top:1px solid var(--stone-200)}
.section-num{
  font-family:'JetBrains Mono',monospace;font-weight:500;
  font-size:12px;letter-spacing:4px;text-transform:uppercase;color:var(--stone-400);
  margin-bottom:14px;
}
h2{
  font-family:'Noto Serif KR',serif;font-weight:700;
  font-size:clamp(22px,3vw,30px);line-height:1.3;
  color:var(--stone-900);letter-spacing:-.3px;
}
p.lede{margin-top:16px;font-size:16px;line-height:1.82;color:var(--stone-700);max-width:680px}
p.lede + .block,p.lede + .design,p.lede + .note,p.lede + .callout{margin-top:30px}
.block-label{
  font-family:'JetBrains Mono',monospace;font-weight:500;
  font-size:11.5px;letter-spacing:.5px;text-transform:uppercase;color:var(--stone-500);
  margin:30px 0 9px;
}
.prose{margin-top:14px;font-size:15px;line-height:1.82;color:var(--stone-700)}
.prose + .block-label{margin-top:24px}

/* ── code block (dark terminal card) ── */
.block.code{
  background:linear-gradient(160deg,var(--code-bg-a),var(--code-bg-b));
  border:1px solid #20262c;border-radius:10px;overflow:hidden;
  box-shadow:0 1px 2px rgba(31,26,16,.06),0 8px 24px rgba(31,26,16,.05);
}
.block.code .bar{
  display:flex;align-items:center;gap:7px;
  padding:11px 15px;border-bottom:1px solid #20262c;background:rgba(255,255,255,.015);
}
.block.code .dot{width:11px;height:11px;border-radius:50%}
.dot.r{background:#ff5f56}.dot.y{background:#ffbd2e}.dot.g{background:#27c93f}
.block.code .bar-label{
  margin-left:8px;font-family:'JetBrains Mono',monospace;font-size:11px;
  letter-spacing:.3px;color:#5d6873;text-transform:lowercase;
}
.block.code pre{
  margin:0;padding:17px 19px;overflow-x:auto;
  font-family:'JetBrains Mono',monospace;font-size:13px;line-height:1.85;
  color:#cdd6df;
}
.block.code pre .c-cmd{color:#9ad08f}
.block.code pre .c-flag{color:#e0c275}
.block.code pre .c-key{color:#82aaff}
.block.code pre .c-str{color:#c3e88d}
.block.code pre .c-cmt{color:#5d6873}

/* ── design block ── */
.design{
  background:var(--cream);border:1px solid var(--stone-200);border-radius:12px;
  padding:26px 28px 28px;
}
.design .goal{
  display:flex;gap:10px;align-items:flex-start;
  font-family:'Noto Serif KR',serif;font-weight:700;font-size:18px;line-height:1.5;
  color:var(--stone-900);padding-bottom:20px;border-bottom:1px solid var(--stone-200);
}
.design .goal .ico{font-size:18px;line-height:1.5}
.design .sub-label{
  font-family:'JetBrains Mono',monospace;font-weight:500;
  font-size:11px;letter-spacing:.5px;text-transform:uppercase;color:var(--stone-400);
  margin:22px 0 12px;display:flex;align-items:center;gap:7px;
}
.principles{display:grid;gap:10px}
.principles .pr{
  display:flex;gap:13px;align-items:flex-start;
  font-size:14.5px;line-height:1.7;color:var(--stone-700);
}
.principles .pr .n{
  flex:0 0 auto;width:23px;height:23px;border-radius:6px;
  background:var(--moss);color:#fff;
  font-family:'JetBrains Mono',monospace;font-size:12px;font-weight:500;
  display:flex;align-items:center;justify-content:center;margin-top:1px;
}
.components{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.components .cmp{
  background:var(--stone-100);border:1px solid var(--stone-200);border-radius:9px;
  padding:17px 18px;
}
.components .cmp .ico{font-size:22px;display:block;margin-bottom:9px}
.components .cmp .nm{
  font-family:'JetBrains Mono',monospace;font-weight:500;font-size:13px;
  color:var(--stone-900);margin-bottom:6px;
}
.components .cmp .ds{font-size:13.5px;line-height:1.65;color:var(--stone-600,#6b6150)}

/* ── note (cream memo, moss left border) ── */
.note{
  background:var(--cream);border:1px solid var(--stone-200);
  border-left:3px solid var(--moss);border-radius:0 9px 9px 0;
  padding:18px 22px;font-size:14.5px;line-height:1.72;color:var(--stone-700);
}
.note strong{color:var(--stone-900);font-weight:700}
.note .star{color:var(--moss);font-weight:700}
.note ul{margin:8px 0 0 2px;padding:0;list-style:none}
.note li{position:relative;padding-left:18px;margin-top:5px}
.note li::before{content:"·";position:absolute;left:4px;color:var(--moss);font-weight:700}

/* ── callout (after block) ── */
.callout{
  margin-top:18px;background:var(--cream);
  border-left:3px solid var(--moss);border-radius:0 8px 8px 0;
  padding:14px 20px;font-size:14px;line-height:1.7;color:var(--stone-700);
}
.callout strong{color:var(--stone-900)}

/* ── ref table ── */
.ref-table{
  margin-top:24px;width:100%;border-collapse:collapse;
  border:1px solid var(--stone-200);border-radius:8px;overflow:hidden;font-size:13.5px;
}
.ref-table th,.ref-table td{
  text-align:left;padding:9px 14px;border-bottom:1px solid var(--stone-200);
  vertical-align:top;
}
.ref-table th{
  font-family:'JetBrains Mono',monospace;font-weight:500;font-size:11px;
  letter-spacing:.4px;text-transform:uppercase;color:var(--stone-400);
  background:var(--cream);
}
.ref-table td code{background:var(--stone-100)}
.ref-table tr:last-child td{border-bottom:none}
.table-scroll{max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}
.table-scroll .ref-table{min-width:760px}

/* ── footer ── */
footer{
  border-top:1px solid var(--stone-200);background:var(--stone-200);
  padding:46px 0;margin-top:8px;
}
footer .container{font-size:13.5px;color:var(--stone-500);line-height:1.8}
footer a{color:var(--stone-700)}
footer .links{margin-top:10px;display:flex;flex-wrap:wrap;gap:18px}
footer .links a{font-family:'JetBrains Mono',monospace;font-size:12px;letter-spacing:.3px}

@media(max-width:640px){
  .components{grid-template-columns:1fr}
  .hero{padding:54px 0 40px}
  .ref-table th,.ref-table td{padding:8px 10px;overflow-wrap:anywhere}
  .ref-table td code{white-space:normal;overflow-wrap:anywhere}
}
</style>
</head>
"""
HEAD = HEAD.replace(
    "<title>oh-my-wiki __VERSION__ — 따라 하는 위키 셋업</title>",
    f"<title>oh-my-wiki v{VERSION} — 따라 하는 위키 셋업</title>",
    1,
)


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────
def esc(s: str) -> str:
    return html.escape(s, quote=False)


def render_block(cmd: dict) -> str:
    """Render one block: kind = code (default) | design | note."""
    kind = cmd.get("kind", "code")
    label = cmd.get("label", "")
    label_html = f'<div class="block-label">{esc(label)}</div>' if label else ""

    if kind == "design":
        d = cmd["design"]
        goal = (
            f'<div class="goal"><span class="ico">🎯</span><span>{esc(d["goal"])}</span></div>'
        )
        princ = ""
        if d.get("principles"):
            items = "".join(
                f'<div class="pr"><span class="n">{i}</span><span>{esc(p)}</span></div>'
                for i, p in enumerate(d["principles"], 1)
            )
            princ = (
                '<div class="sub-label">📏 PRINCIPLES</div>'
                f'<div class="principles">{items}</div>'
            )
        comps = ""
        if d.get("components"):
            cards = "".join(
                f'<div class="cmp"><span class="ico">{esc(ico)}</span>'
                f'<div class="nm">{esc(nm)}</div><div class="ds">{esc(ds)}</div></div>'
                for ico, nm, ds in d["components"]
            )
            comps = (
                '<div class="sub-label">🧱 COMPONENTS</div>'
                f'<div class="components">{cards}</div>'
            )
        return f'{label_html}<div class="design">{goal}{princ}{comps}</div>'

    if kind == "note":
        return f'{label_html}<div class="note">{cmd["text"]}</div>'

    # default: code (dark terminal card)
    text = esc(cmd.get("text", ""))
    bar_label = cmd.get("bar", "terminal")
    return (
        f'{label_html}<div class="block code">'
        f'<div class="bar"><span class="dot r"></span><span class="dot y"></span>'
        f'<span class="dot g"></span><span class="bar-label">{esc(bar_label)}</span></div>'
        f"<pre>{text}</pre></div>"
    )


def render_section(s: dict) -> str:
    parts = [
        f'<section id="step-{s["num"]}">',
        '<div class="container">',
        f'<div class="section-num">{esc(s["num"])}</div>',
        f'<h2>{esc(s["title"])}</h2>',
    ]
    if s.get("lede"):
        parts.append(f'<p class="lede">{s["lede"]}</p>')
    for cmd in s.get("commands", []):
        if cmd.get("prose"):
            parts.append(f'<div class="prose">{cmd["prose"]}</div>')
        parts.append(render_block(cmd))
        if cmd.get("callout"):
            parts.append(f'<div class="callout">{cmd["callout"]}</div>')
    if s.get("after"):
        parts.append(s["after"])
    parts.append("</div></section>")
    return "\n".join(parts)


def _quick_reference_table() -> str:
    rows = "".join(
        "<tr>"
        f"<td><code>omw {esc(op.name)}</code></td>"
        f"<td>{esc(OP_SUMMARY_KO[op.name])}</td>"
        "</tr>"
        for op in CLI_OPS
    )
    skills = " · ".join(f"<code>{esc(op.name)}</code>" for op in SKILL_OPS)
    return (
        '<div class="table-scroll"><table class="ref-table">'
        "<tr><th>CLI 명령</th><th>한 줄 설명</th></tr>"
        + rows
        + "</table></div>"
        + '<div class="callout" style="margin-top:24px">'
        + f"세션 스킬 작업 {SKILL_COUNT}개: {skills}. 정확한 플래그는 "
        + "<code>omw &lt;command&gt; --help</code>로 확인합니다. 전체 설명은 기능 레퍼런스를 참고하세요."
        + "</div>"
    )


QUICK_REFERENCE_TABLE = _quick_reference_table()


# ─────────────────────────────────────────────────────────────────────────────
# SECTIONS — Korean focused showcase, verbatim command blocks from TUTORIAL.ko.md
# ─────────────────────────────────────────────────────────────────────────────
SECTIONS: list[dict] = [
    dict(
        num="STEP 01",
        title="설치",
        lede="환경에 맞는 경로 하나를 골라 설치합니다. 어떤 경로든 끝나면 "
        "<code>omw doctor</code>로 연결 상태를 확인합니다.",
        commands=[
            {
                "label": "PATH A — PyPI (pipx / pip) · 권장",
                "bar": "bash",
                "text": "pipx install oh-my-wiki   # 또는: pip install oh-my-wiki\n"
                "omw setup agents",
                "callout": "설치 즉시 <code>omw</code> 커맨드를 사용할 수 있습니다.",
            },
            {
                "label": "PATH B — git clone + install script (개발자)",
                "bar": "bash",
                "text": "git clone https://github.com/dandacompany/oh-my-wiki\n"
                "cd oh-my-wiki\n"
                "bash bin/install.sh",
                "callout": "인스톨러가 Python 3.10+ 확인, "
                "<code>pip install -e \".\"</code>, "
                "<code>~/.claude/skills/oh-my-wiki</code>·<code>omw</code> symlink 생성(멱등성), "
                "<code>pytest -q</code> 검증을 수행합니다. 재실행해도 안전하며, "
                "<code>--force</code>로 프롬프트 없이 교체합니다.",
            },
            {
                "label": "PATH C — Skills CLI",
                "bar": "bash",
                "text": "skills add dandacompany/oh-my-wiki@oh-my-wiki -g -y --copy -a claude-code",
                "callout": "스킬만 설치됩니다. <code>omw</code> CLI는 처음 사용 시 설치됩니다 — "
                "에이전트에 <code>omw 셋업 점검해줘</code>라고 하면 CLI 프리플라이트가 설치합니다. "
                "또는 지금 <code>pipx install oh-my-wiki</code>.",
            },
            {
                "label": "설치 확인 — omw doctor",
                "bar": "terminal",
                "text": "omw doctor",
            },
            {
                "label": "성공하면 보이는 것 (vault가 있을 때)",
                "bar": "output",
                "text": "omw home:   ~/.omw  ok\n"
                "registry:   ~/.omw/registry.db  ok\n"
                "  * demo (wiki/markdown) ~/.omw/vaults/demo",
                "callout": "새 머신에서 <code>omw setup</code> 전이라면 "
                "<code>missing (run: omw setup)</code>으로 표시됩니다. "
                "<code>doctor</code>는 각 컴포넌트를 찾으면 <code>ok</code>를, 없으면 무엇이 빠졌는지 보고합니다.",
            },
            {
                "label": "명령 둘러보기 · 버전 · 업그레이드",
                "bar": "terminal",
                "text": "omw help              # 모든 명령을 라이프사이클 단계별로 정리해 보기\n"
                f"omw version           # → omw {VERSION}   (omw -v / --version 동일)\n"
                "omw update            # 환경에 맞게 자가 업그레이드 (omw update --check 로 점검만)",
                "callout": "<code>omw help</code>·<code>omw -h</code>는 명령을 "
                "capture→structure→synthesize→retrieve→maintain→use 단계로 묶어 보여줍니다"
                "(<code>[CLI]</code> 직접 실행 / <code>[skill]</code> 세션 스킬 수행). "
                "<code>omw update</code>는 설치 방식을 감지해 알맞게 올리고, 설정·볼트는 건드리지 않습니다.",
            },
        ],
    ),
    dict(
        num="STEP 02",
        title="첫 위키",
        lede="설정 마법사로 첫 vault(위키 보관함)를 만들고, 상태와 lint(검사)로 깨끗한 시작점을 확인합니다.",
        commands=[
            {
                "label": "설정 마법사 실행",
                "bar": "terminal",
                "text": "omw setup",
                "callout": "첫 vault, 검색 provider, persona를 구성하는 대화형 마법사입니다. "
                "기본값을 그대로 받아들이면 빠르게 시작합니다. 이후 "
                "<code>omw setup vault</code>·<code>omw setup personas</code>로 개별 섹션을 다시 조정합니다.",
            },
            {
                "label": "상태 확인 — omw status",
                "bar": "terminal",
                "text": "omw status",
            },
            {
                "label": "성공하면 보이는 것 (깨끗한 머신)",
                "bar": "json",
                "text": "{\n"
                '  "vault_count": 0,\n'
                '  "active": null,\n'
                '  "needs": "setup",\n'
                '  "vaults": []\n'
                "}",
                "callout": "<code>needs: \"setup\"</code>은 깨끗한 머신의 정상 화면입니다. "
                "소스 트리에서 실행하면 <code>data/registry.db</code> 때문에 "
                "<code>needs</code>가 <code>\"migrate\"</code>로 표시되며, 이는 개발 트리에서만 나타납니다.",
            },
            {
                "label": "첫 vault 만들기",
                "bar": "terminal",
                "text": "omw vault create demo --mode wiki",
                "callout": "용도에 따라 <code>wiki</code> · <code>memo</code> · <code>personal</code> · "
                "<code>book</code> · <code>business</code> · <code>github-codebase</code> · "
                "<code>website</code>를 고를 수 있습니다. 각 모드는 목적에 맞는 첫 폴더와 index를 만듭니다.",
            },
            {
                "label": "성공하면 보이는 것",
                "bar": "json",
                "text": "{\n"
                '  "created": "demo",\n'
                '  "path": "~/.omw/vaults/demo",\n'
                '  "mode": "wiki",\n'
                '  "type": "markdown"\n'
                "}",
            },
            {
                "label": "활성 상태 확인 — omw vault list",
                "bar": "json",
                "text": "[\n"
                "  {\n"
                '    "name": "demo",\n'
                '    "path": "~/.omw/vaults/demo",\n'
                '    "mode": "wiki",\n'
                '    "type": "markdown",\n'
                '    "is_active": true\n'
                "  }\n"
                "]",
            },
            {
                "label": "노트 추가 (Claude / Codex / Gemini 세션에서)",
                "bar": "ai session",
                "text": "ingest this\n\n"
                'Andrej Karpathy calls the LLM Wiki a "compounding knowledge artifact". Every\n'
                "source gets saved verbatim to raw/, a summary lands at wiki/summaries/, and\n"
                "the entities and concepts that appeared get their own pages. 10–15 page touches\n"
                "per ingest is normal.",
                "callout": "스킬이 제목, slug, 태그, 저장 위치를 제안합니다. 확인하면 저장됩니다.",
            },
            {
                "label": "lint 검사 — omw lint",
                "bar": "terminal",
                "text": "omw lint",
            },
            {
                "label": "성공하면 보이는 것 (문제 없는 vault)",
                "bar": "json",
                "text": "{\n"
                '  "vault_id": 1,\n'
                '  "vault_path": "~/.omw/vaults/demo",\n'
                '  "frontmatter_issues": [],\n'
                '  "drift": { "missing_files": [], "mtime_drift": [] },\n'
                '  "links": {\n'
                '    "broken": [],\n'
                '    "orphans": [],\n'
                '    "index_drift": { "missing_from_index": [], "dangling_in_index": [] },\n'
                '    "contradictions": [],\n'
                '    "supersedes": [],\n'
                '    "superseded_unmarked": [],\n'
                '    "link_suggestions": []\n'
                "  },\n"
                '  "auto_fix_hints": []\n'
                "}",
            },
            {
                "kind": "note",
                "text": "<span class='star'>★ 읽는 법</span> — "
                "<strong>frontmatter_issues: []</strong>는 모든 페이지가 필수 필드 검사를 통과했다는 뜻입니다."
                "<ul>"
                "<li><strong>links</strong> 키들(broken·orphans·index_drift·contradictions·supersedes·"
                "superseded_unmarked·link_suggestions)은 vault의 구조 건강 상태를 알려줍니다.</li>"
                "<li><strong>drift</strong>는 디스크에 있지만 인덱스에 없는 파일을 보고합니다.</li>"
                "<li><strong>auto_fix_hints</strong>는 문제가 발견될 때 실행 가능한 해결 방법을 제시합니다.</li>"
                "</ul>",
            },
        ],
    ),
    dict(
        num="STEP 03",
        title="페이지 규약 (스키마)",
        lede="글의 종류(인물·개념·논문 등)마다 갖춰야 할 항목이 정해져 있습니다. 이 '양식'을 스키마라고 부르며, "
        "덕분에 위키가 한결같이 정돈됩니다. 13개 기본 종류를 살펴보고, 그중 entity(대상) 종류를 자세히 봅니다.",
        commands=[
            {
                "kind": "note",
                "text": "<span class='star'>★ 엔티티(entity)란?</span> — "
                "위키에 등장하는 <strong>이름을 가진 고유한 대상</strong>입니다. 인물·도구·회사·개념처럼요. "
                "예를 들어 '안드레이 카르파시'(인물)나 'LLM 위키'(개념)가 각각 하나의 엔티티이고, 저마다 자기 페이지를 가집니다. "
                "다른 글에서 이 이름이 나오면 그 페이지로 자동 연결됩니다(STEP 07). "
                "<code>entity</code>는 그런 대상 페이지의 한 종류이고, 아래에서 그 양식을 살펴봅니다.",
            },
            {
                "label": "타입 나열 — omw schema list",
                "bar": "terminal",
                "text": "omw schema list",
            },
            {
                "label": "13개 타입",
                "bar": "output",
                "text": "article, book, comparison, concept, doc, entity, link, meta, note,\n"
                "paper, summary, synthesis, video",
                "callout": "각 항목은 <code>type</code>, <code>required_fields</code>, "
                "<code>required_sections</code>, <code>field_types</code>, "
                "<code>allowed_values</code>를 가진 스키마 객체입니다.",
            },
            {
                "label": "entity 타입 상세 — omw schema show entity",
                "bar": "terminal",
                "text": "omw schema show entity",
            },
            {
                "label": "성공하면 보이는 것",
                "bar": "json",
                "text": "{\n"
                '  "type": "entity",\n'
                '  "required_fields": ["title", "date", "type", "tags"],\n'
                '  "required_sections": ["## Summary"],\n'
                '  "field_types": {\n'
                '    "tags": "list",\n'
                '    "title": "str",\n'
                '    "date": "str",\n'
                '    "review": "dict",\n'
                '    "aliases": "list"\n'
                "  },\n"
                '  "allowed_values": {\n'
                '    "confidence": ["high", "medium", "low"],\n'
                '    "status": ["draft", "inbox", "processed", "raw", "superseded", "meta"]\n'
                "  }\n"
                "}",
                "callout": "모든 entity 페이지는 본문에 <code>## Summary</code> 섹션이 있어야 합니다. "
                "<code>confidence</code>는 high·medium·low를, <code>status</code>는 "
                "<code>allowed_values</code> 목록값을 허용합니다.",
            },
            {
                "label": "vault별 스키마 오버라이드",
                "bar": "tree",
                "text": "~/.omw/vaults/demo/\n"
                "└── schemas/\n"
                "    └── entity.yml   ← overrides the built-in entity schema for this vault only",
                "callout": "<code>&lt;vault&gt;/schemas/</code>의 파일이 패키지 루트의 내장 "
                "<code>schemas/</code>보다 우선합니다. 공유 기본값을 건드리지 않고 특정 프로젝트에 "
                "커스텀 타입을 추가하거나 필드 규칙을 강화합니다.",
            },
        ],
    ),
    dict(
        num="STEP 04",
        title="신뢰도와 대체",
        lede="각 페이지에는 그 내용을 얼마나 믿을 수 있는지 나타내는 신뢰도(<code>confidence</code>: high·medium·low)를 붙일 수 있습니다. "
        "또 더 나은 페이지가 생기면 옛 페이지를 지우지 않고 '대체됨(<code>superseded</code>)'으로 표시해 기록을 남깁니다.",
        commands=[
            {
                "kind": "note",
                "text": "<span class='star'>★ 신뢰도(confidence)는 왜 쓰나요?</span> — "
                "모든 메모가 똑같이 확실하지는 않습니다. 직접 검증한 내용도 있고, 한 번 듣고 적어 둔 것도 있죠. "
                "<strong>high·medium·low</strong>로 그 확실함을 표시해 두면, 나중에 무엇을 믿고 인용할지, "
                "무엇을 더 자주 다시 들여다볼지 판단하는 기준이 생깁니다. "
                "실제로 다음 단계(리뷰 주기)에서 신뢰도가 높은 글은 더 드물게, 낮은 글은 더 자주 다시 보도록 자동 조정됩니다.",
            },
            {
                "label": "old-method.md를 llm-wiki로 supersede",
                "bar": "terminal",
                "text": "omw supersede wiki/concepts/old-method.md --by llm-wiki",
            },
            {
                "label": "성공하면 보이는 것",
                "bar": "json",
                "text": "{\n"
                '  "relpath": "wiki/concepts/old-method.md",\n'
                '  "status": "superseded",\n'
                '  "superseded_by": "llm-wiki"\n'
                "}",
            },
            {
                "label": "old-method.md에 작성되는 frontmatter",
                "bar": "yaml",
                "text": "status: superseded\n"
                "superseded_by: llm-wiki",
                "callout": "<code>omw lint</code>는 본문에 \"outdated\"·\"replaced\"로 비공식 설명되어 "
                "있지만 이 필드가 없는 페이지를 <code>superseded_unmarked</code> 키 아래에 표시합니다.",
            },
            {
                "label": "중복 두 페이지를 하나로 — omw merge",
                "bar": "terminal",
                "text": "omw merge wiki/concepts/dup.md wiki/concepts/keeper.md\n"
                "# 통합본·tombstone을 .proposed.md로 스테이징 → 검토 후:\n"
                "omw merge --apply wiki/concepts/keeper.md.proposed.md",
                "callout": "<strong>대체(supersede)</strong>가 한 페이지를 다른 페이지로 가리키는 것이라면, "
                "<strong>통합(merge)</strong>은 두 페이지를 하나로 합칩니다 — 본문을 이어붙이고, 사라지는 쪽 "
                "slug을 살아남는 페이지의 <code>aliases</code>에 등록해 기존 <code>[[링크]]</code>가 그대로 "
                "동작합니다. 모든 변경은 <code>.proposed.md</code>로 먼저 제안되고 <code>--apply</code> 전까지 "
                "원본은 그대로입니다. 중복 후보는 <code>omw lint</code>가 제안합니다.",
            },
        ],
    ),
    dict(
        num="STEP 05",
        title="리뷰 주기",
        lede="각 페이지는 '언제 다시 볼지'를 스스로 기억합니다. 글 맨 위 메타정보 영역인 frontmatter의 <code>review:</code> 블록에 적힙니다. "
        "신뢰도가 높을수록 간격이 길어집니다. 믿을 만한 내용은 자주 볼 필요가 없으니까요. "
        "high는 90일, medium은 30일, low는 7일마다 다시 검토하도록 안내합니다.",
        commands=[
            {
                "label": "llm-wiki.md (high-confidence) review 완료 처리",
                "bar": "terminal",
                "text": "omw review done wiki/concepts/llm-wiki.md --grade pass --today 2026-06-01",
            },
            {
                "label": "성공하면 보이는 것",
                "bar": "json",
                "text": "{\n"
                '  "relpath": "wiki/concepts/llm-wiki.md",\n'
                '  "review": { "last": "2026-06-01", "due": "2026-08-30", "interval_days": 90 }\n'
                "}",
                "callout": "<code>high</code> confidence → 90일 간격 → 만료일 <code>2026-08-30</code>.",
            },
            {
                "label": "review 대상 조회 (미래 날짜 시뮬레이션)",
                "bar": "terminal",
                "text": "omw review due --today 2026-09-01",
                "callout": "<code>{relpath, due, interval_days, confidence}</code> 목록이 반환됩니다. "
                "<code>review:</code> 블록이 없는 페이지는 <code>due: null</code>로 표시되며 가장 앞에 정렬됩니다. "
                "한 번도 검토되지 않았으므로 주의가 필요합니다.",
            },
        ],
    ),
    dict(
        num="STEP 06",
        title="전문 검색 & 메신저 API",
        lede="위키 안의 글을 빠르게 찾는 검색입니다. 제목·요약·태그·본문을 함께 살핍니다. "
        "세션에서 자연어로 묻거나, <code>omw serve</code>로 로컬 전용 검색 API(<code>POST /query</code>)를 띄워 다른 앱에서 가져올 수 있습니다.",
        commands=[
            {
                "label": "vault 인덱싱 방식",
                "bar": "fts5",
                "text": "title + summary + tags + body  →  SQLite FTS5 (BM25)\n"
                "FTS5 미지원 시  →  토큰 스코어 기반 자동 폴백",
                "callout": "세션에서 \"내 위키에서 X에 대해 뭐라고 해?\"라고 말하면 스킬이 FTS5로 검색하고 "
                "LLM이 결과를 재순위 매깁니다. <code>omw serve</code>는 서버에 LLM 없이 검색만 수행합니다.",
            },
            {
                "label": "인증 토큰 생성 (~/.omw/.env에 OMW_SERVE_TOKEN으로 저장)",
                "bar": "terminal",
                "text": "omw setup serve --generate-token",
            },
            {
                "label": "서버 시작 — omw serve",
                "bar": "terminal",
                "text": "omw serve",
                "callout": "서버는 <code>http://127.0.0.1:8765</code>(localhost 전용)에서 실행됩니다. "
                "<code>POST /query</code>는 인증 필요, <code>GET /health</code>는 인증 불필요, "
                "<code>GET /query</code>는 405를 반환합니다.",
            },
            {
                "label": "curl — health(인증 없음) + query(POST + bearer)",
                "bar": "bash",
                "text": "# health (no auth)\n"
                "curl -s http://127.0.0.1:8765/health\n\n"
                "# query (POST + bearer token)\n"
                "curl -s -X POST http://127.0.0.1:8765/query \\\n"
                '  -H "Authorization: Bearer $OMW_SERVE_TOKEN" \\\n'
                '  -H "Content-Type: application/json" \\\n'
                '  -d \'{"text": "compounding knowledge", "limit": 5}\'',
                "callout": "전체 요청/응답 JSON 형식과 Slack·Telegram·Discord 어댑터 스케치는 "
                "<code>references/messenger-api.md</code>에 있습니다.",
            },
            {
                "kind": "note",
                "text": "<span class='star'>★ 구분</span> — "
                "<strong>omw search</strong>는 별개입니다. 외부 provider"
                "(brave·tavily·exa·firecrawl·brightdata)를 통한 <strong>웹 검색</strong>이며, "
                "vault 내부를 검색하지 않습니다. provider 미설정 시 "
                "<code>omw setup search</code>를 실행합니다.",
            },
        ],
    ),
    dict(
        num="STEP 07",
        title="엔티티 자동 링크",
        lede="어떤 글이 다른 대상(엔티티 — 인물·도구·개념 등)을 이름으로만 언급하고 연결은 안 걸어 둔 경우, "
        "oh-my-wiki가 그 언급을 찾아 자동으로 위키 내부 링크(wikilink, <code>[[...]]</code> 형태)를 걸어 줍니다.",
        commands=[
            {
                "label": "링크 없는 언급 감지 — omw links suggest",
                "bar": "terminal",
                "text": "omw links suggest",
            },
            {
                "label": "성공하면 보이는 것 (2건)",
                "bar": "json",
                "text": "[\n"
                "  {\n"
                '    "src_relpath": "wiki/concepts/llm-wiki.md",\n'
                '    "target_slug": "andrej-karpathy",\n'
                '    "target_relpath": "wiki/entities/andrej-karpathy.md",\n'
                '    "mention": "Andrej Karpathy",\n'
                '    "position": 145\n'
                "  },\n"
                "  {\n"
                '    "src_relpath": "wiki/entities/andrej-karpathy.md",\n'
                '    "target_slug": "llm-wiki",\n'
                '    "target_relpath": "wiki/concepts/llm-wiki.md",\n'
                '    "mention": "LLM Wiki",\n'
                '    "position": 88\n'
                "  }\n"
                "]",
                "callout": "<code>llm-wiki.md</code> 위치 145에서 \"Andrej Karpathy\"가, "
                "<code>andrej-karpathy.md</code> 위치 88에서 \"LLM Wiki\"가 wikilink 없이 언급됩니다. "
                "두 경우 모두 vault에 일치하는 페이지가 존재합니다.",
            },
            {
                "label": "링크 삽입 — omw links link",
                "bar": "terminal",
                "text": "omw links link wiki/concepts/llm-wiki.md --to andrej-karpathy",
            },
            {
                "label": "성공하면 보이는 것",
                "bar": "json",
                "text": "{\n"
                '  "relpath": "wiki/concepts/llm-wiki.md",\n'
                '  "target_slug": "andrej-karpathy",\n'
                '  "mention": "Andrej Karpathy",\n'
                '  "inserted": "[[andrej-karpathy|Andrej Karpathy]]"\n'
                "}",
                "callout": "해당 언급을 <code>[[andrej-karpathy|Andrej Karpathy]]</code>로 제자리에서 재작성합니다.",
            },
            {
                "kind": "note",
                "text": "<span class='star'>★ 한국어 조사 매칭</span> — "
                "본문에 <strong>안드레이 카르파시가 이 방법을 제안했다.</strong>처럼 조사 "
                "<code>가</code>가 이름에 붙어 있어도, <code>omw links suggest</code>가 "
                "<code>안드레이 카르파시가</code>를 <code>안드레이 카르파시</code> slug와 매칭하고, "
                "<code>omw links link</code>는 다음처럼 삽입합니다."
                "<ul>"
                "<li><code>[[…|안드레이 카르파시]]가 이 방법을 제안했다.</code></li>"
                "</ul>"
                "조사는 wikilink 괄호 밖에 남고, 표시 텍스트는 조사 없는 표준 이름입니다.",
            },
        ],
    ),
    dict(
        num="STEP 08",
        title="인라인 필드",
        lede="페이지 본문에 Dataview 스타일 인라인 필드 <code>key:: value</code>를 넣으면 "
        "frontmatter와 함께 파싱·저장·인덱싱됩니다.",
        commands=[
            {
                "label": "본문 인라인 필드 예시",
                "bar": "markdown",
                "text": "owner:: dante\n"
                "status:: draft\n"
                "uses:: [[llm-wiki]]",
            },
            {
                "label": "전체 필드 확인 — omw fields",
                "bar": "terminal",
                "text": "omw fields wiki/concepts/llm-wiki.md",
            },
            {
                "label": "성공하면 보이는 것",
                "bar": "json",
                "text": "{\n"
                '  "relpath": "wiki/concepts/llm-wiki.md",\n'
                '  "frontmatter": {\n'
                '    "title": "LLM Wiki",\n'
                '    "date": "2026-06-01",\n'
                '    "type": "concept",\n'
                '    "tags": ["method"]\n'
                "  },\n"
                '  "inline": { "owner": ["dante"], "status": ["draft"] }\n'
                "}",
                "callout": "wikilink를 참조하는 관계 키(<code>uses</code>, <code>contradicts</code>, "
                "<code>supersedes</code>)는 frontmatter <code>relations:</code>와 똑같이 "
                "관계 그래프(무엇이 무엇과 어떻게 이어지는지)에 함께 반영됩니다.",
            },
        ],
    ),
    dict(
        num="STEP 09",
        title="페르소나 (세션 내, 자연어)",
        lede="여섯 가지 wiki-maintenance persona를 Claude Code / Codex / Gemini 세션에서 자연어로 호출합니다. "
        "별도 커맨드 없이 입력 내용에 따라 스킬이 적절한 persona로 라우팅합니다.",
        commands=[
            {
                "label": "Researcher — in your Claude session, say:",
                "bar": "ai session",
                "text": "autoresearch how does the LLM Wiki pattern compare to Zettelkasten?",
                "callout": "질문을 주장 단위로 분해하고, 주장별 최대 3라운드 검색 후 confidence 태그를 부여하며, "
                "synthesis 초안을 작성해 저장 전에 확인을 요청합니다. → "
                "<code>wiki/syntheses/&lt;slug&gt;.md</code>",
            },
            {
                "label": "Fact-checker — in your Claude session, say:",
                "bar": "ai session",
                "text": "fact-check wiki/concepts/llm-wiki.md",
                "callout": "초안을 원자 단위 주장으로 분해해 웹 검색으로 검증하고, 판정 표"
                "(supported·contradicted·partial·unverifiable)를 "
                "<code>&lt;page&gt;.factcheck.md</code>에 작성합니다.",
            },
            {
                "label": "Wiki-auditor — in your AI session, say:",
                "bar": "ai session",
                "text": "audit my wiki — what is wrong with it?",
                "callout": "lint·유지 상태·그래프를 모아 무엇이 문제인지 우선순위로 진단합니다. 파일은 바꾸지 않습니다.",
            },
            {
                "label": "Wiki-librarian / Curator / Consistency / Terminology — say:",
                "bar": "ai session",
                "text": "tidy the wiki structure            # librarian: 구조 개선 제안\n"
                "curate my index                    # curator: index.md 정리\n"
                "check for contradictions           # consistency-checker\n"
                "build a glossary for my vault      # terminology-manager",
                "callout": "auditor는 문제를 찾고, librarian은 구조 개선을 제안하며, curator는 index를 정리합니다. "
                "consistency-checker와 terminology-manager는 모순과 용어 표류를 점검합니다.",
            },
            {
                "kind": "note",
                "text": "<span class='star'>★ 6종 역할의 공통 모델</span> — "
                "모든 persona는 <strong>제안 → 확인 → 실행</strong>을 따릅니다. "
                "파일을 읽고, 제안 초안을 작성하고, 무엇이 변경될지 보여준 다음 작성합니다. "
                "전체 목록(wiki-auditor·wiki-librarian·curator·fact-checker·consistency-checker·terminology-manager)은 아래 레퍼런스에 있습니다.",
            },
        ],
    ),
    dict(
        num="STEP 10",
        title="프롬프트별 recall",
        lede="물어보는 순간 AI 에이전트가 활성 위키를 자동으로 참고하게 만드는 기능입니다. "
        "<code>omw find</code>를 직접 실행하지 않아도, 프롬프트마다 관련 페이지를 찾아 답변의 근거로 끌어옵니다. "
        "Claude Code · Codex · OpenCode · Gemini · Hermes · OpenClaw 어디서나 동일하게 동작합니다(엔진 하나, 호스트별로 번역).",
        commands=[
            {
                "label": "recall 켜기 — omw setup recall",
                "bar": "terminal",
                "text": "omw setup recall",
                "callout": "<code>omw setup</code> 마법사의 한 섹션이기도 합니다. 모드를 설정하고, "
                "호스트 지침 파일에 안내 블록을 주입하며, 호스트가 지원하는 네이티브 훅을 연결합니다. "
                "Claude Code·Codex는 <strong>SessionStart · UserPromptSubmit · PreToolUse</strong>로 회상하고 "
                "<strong>PreCompact · Stop</strong>에서 같은 프로젝트의 최소 세션 맥락을 임시 저장합니다. 호스트 선택지는 규약 단위로 "
                "묶입니다 — <code>claude</code>(CLAUDE.md) · <code>codex·opencode</code>(AGENTS.md, 한 번만) · "
                "<code>gemini</code>(GEMINI.md) · <code>hermes</code>(프로필) · <code>openclaw</code>(워크스페이스). "
                "Gemini는 SessionStart·BeforeAgent, Hermes는 pre_llm_call 회상 + post_llm_call 캡처, OpenCode·OpenClaw는 TypeScript recall 플러그인을 사용합니다.",
            },
            {
                "label": "세션 임시 캡처 확인·끄기",
                "bar": "terminal",
                "text": "omw recall sessions\n"
                "omw recall sessions --dismiss <id>\n"
                "omw setup recall --session-capture off",
                "callout": "마지막 요청·결과·다룬 파일만 일반적인 비밀값 패턴을 가린 뒤 로컬 registry에 저장합니다. "
                "불러올 때는 실행 지시가 아닌 이스케이프된 JSON 데이터로 구분합니다. "
                "같은 프로젝트에 최대 5개, 30일 보관하며 위키 페이지로 자동 승격하지 않습니다. "
                "Codex에서는 설정 뒤 <code>/hooks</code>에서 새 OMW 사용자 훅을 승인해야 합니다.",
            },
            {
                "label": "완료 세션의 지식 후보 — 검토 후 승인",
                "bar": "terminal",
                "text": "omw setup recall --knowledge-candidates staged\n"
                "omw candidates status\n"
                "omw candidates list\n"
                "omw candidates show <batch-id>\n"
                "omw candidates approve <batch-id>   # 또는 dismiss",
                "callout": "기본값은 <code>off</code>입니다. 권장 <code>staged</code> 모드는 결정·선호·검증된 사실·재사용 절차·원인+수정 쌍을 후보로 묶지만, 승인 전에는 vault 파일을 쓰지 않습니다. "
                "<code>Stop</code>은 캡처만 하고 <code>PreCompact</code> 또는 다음 세션 경계에서 한 번 분석합니다. 대기 후보는 30일 뒤 만료됩니다. "
                "<code>auto-raw</code>는 신뢰도 높은 새 항목만 비공개 raw로 쓰는 별도 선택입니다.",
            },
            {
                "label": "설정 두 축 — recall.mode (언제) · recall.strategy (어떻게)",
                "bar": "config",
                "text": "recall.mode      auto       # 프롬프트마다 검색 → 강한 히트 시 <omw-recall> 블록 주입\n"
                "                 advisory   # 강한 히트 시 동일하게 주입; 히트 없을 때만 omw find 넛지로 폴백\n"
                "                 off\n\n"
                "recall.strategy  fts        # 키워드 + 한국어 조사 정규화 (결정론적, 기본값)\n"
                "                 embedding  # 시맨틱 벡터 검색 via sqlite-vec (provider 필요: omw setup recall --embed-provider openai|fake)\n"
                "                            # provider 미설정 시 키워드(FTS) 결과로 폴백\n"
                "                 hybrid     # fts + embedding RRF 융합; embedding provider 미설정 시 사실상 FTS\n"
                "                 llm        # 에이전트 위임 — 훅이 <omw-recall> 지시 방출, 세션 에이전트가 검색\n"
                "                            # submode: route(키워드vs시맨틱 판단 후 omw find) · generative(후보 읽어 필터)\n"
                "                            # 알 수 없는 전략은 fts로 폴백",
                "callout": "<code>mode</code>는 <strong>언제</strong> 위키를 참고할지, "
                "<code>strategy</code>는 <strong>어떻게</strong> 후보를 찾을지를 정합니다. "
                "<code>auto</code>와 <code>advisory</code> 모두 강한 히트가 있으면 <code>&lt;omw-recall&gt;</code>을 주입합니다. "
                "차이는 히트가 없을 때: <code>auto</code>는 조용히 넘어가고, <code>advisory</code>는 "
                "<code>omw find</code>를 권유하는 넛지를 남깁니다.",
            },
            {
                "label": "auto 모드에서 프롬프트에 주입되는 블록 예시",
                "bar": "omw-recall",
                "text": "<omw-recall> 활성 omw 위키에 관련 페이지가 있습니다 — 답변의 근거/출처로 활용하세요:\n"
                "- Demand Forecasting — wiki/syntheses/demand-forecasting.md [arima,prophet] (score 1.9)\n"
                "</omw-recall>",
                "callout": "제목·경로·태그·인용 점수가 함께 들어가, 에이전트가 곧바로 출처로 인용할 수 있습니다.",
            },
            {
                "kind": "note",
                "text": "<span class='star'>★ recall 품질의 비결</span> — "
                "recall은 좋은 <strong>title·aliases·tags·summary</strong> frontmatter에서 좋아집니다. "
                "FTS5는 본문도 검색하며, 품질 게이트는 이름·별칭·태그·요약·제한된 본문 근거와 의미 검색의 일치를 함께 확인합니다.",
            },
            {
                "label": "위키 연결 탐색 · 유지보수 상태 확인",
                "bar": "terminal",
                "text": "omw connections [--vault]                 # 링크 그래프 커뮤니티 감지\n"
                "                                          # → 커뮤니티 · 브리지(예상치 못한 연결) · 허브 (JSON)\n\n"
                "omw maint status [--vault] [--exit-code]  # 지식 유지보수 상태\n"
                "                                          # → 만료·오래된 페이지 + lint 이슈 집계, 한 줄 넛지\n"
                "                                          # --exit-code: 작업 필요 시 1 반환 (cron 친화적)\n\n"
                "omw report [--vault] [--no-reindex]       # 전체 현황·건강 한눈에 (대시보드)\n"
                "                                          # → 볼트 요약 + 활성 볼트 구성 + 건강 등급 + 다음 행동\n"
                "                                          # --json: 구조화 출력",
                "callout": "<code>omw connections</code>는 링크 그래프에서 커뮤니티·브리지·허브를 결정론적으로 감지합니다. "
                "브리지(크로스 커뮤니티 링크)는 '뜻밖의 연결'을 발견하는 단서가 됩니다. "
                "<code>omw maint status</code>는 세션 시작 recall 프리앰블에도 표시됩니다. "
                "<code>omw report</code>는 이 모든 신호를 한 화면 대시보드로 모아 볼트 등급"
                "(<code>GOOD</code>/<code>FAIR</code>/<code>NEEDS WORK</code>)까지 보여줍니다.",
            },
        ],
    ),
    dict(
        num="STEP 11",
        title="Obsidian · Logseq에서 열기",
        lede="<code>omw setup viewer</code>로 기본 뷰어를 지정하고, "
        "<code>omw view</code>로 활성 vault·페이지·검색 결과를 URI 스킴으로 바로 엽니다. "
        "별도 앱 확장 없이 동작합니다.",
        commands=[
            {
                "label": "기본 뷰어 설정 (최초 1회)",
                "bar": "terminal",
                "text": "omw setup viewer",
                "callout": "obsidian 또는 logseq 중 기본 뷰어를 고르고 설정 스캐폴드를 생성합니다. "
                "선택한 값은 <code>~/.omw/config.yaml</code>에 저장됩니다.",
            },
            {
                "label": "페이지·검색을 뷰어로 열기",
                "bar": "terminal",
                "text": "omw view                                       # 활성 vault\n"
                "omw view wiki/concepts/llm-wiki.md            # 특정 페이지\n"
                "omw view --search \"compounding knowledge\"      # 검색 결과\n"
                "omw view wiki/concepts/llm-wiki.md --print    # URI만 출력",
                "callout": "<code>--viewer logseq</code>으로 뷰어를 일회성으로 바꿀 수 있습니다. "
                "<code>--print</code>는 앱을 실행하지 않고 URI를 stdout에 출력합니다.",
            },
            {
                "kind": "note",
                "text": "<span class='star'>★ 공개 여부</span> — "
                "페이지를 메신저 API(<code>omw serve</code>)로 노출하려면 먼저 "
                "<code>omw visibility set wiki/concepts/llm-wiki.md public</code>으로 공개 설정이 필요합니다. "
                "기본값은 <strong>private</strong>이므로 명시적으로 설정하지 않으면 노출되지 않습니다.",
            },
        ],
    ),
    dict(
        num="STEP 12",
        title="웹에서 가져오기",
        lede="URL 하나를 즉시 raw/로 가져오거나(<code>omw fetch</code>), "
        "여러 URL을 쌓아 두었다가 한 번에 수집합니다(<code>omw inbox</code>). "
        "두 방법 모두 LLM 없이 원본 그대로 저장합니다.",
        commands=[
            {
                "label": "URL 즉시 수집 — omw fetch",
                "bar": "terminal",
                "text": "omw fetch https://example.com/article\n"
                "omw fetch https://youtu.be/VIDEO_ID\n"
                "omw fetch https://example.com/spa --backend chromium",
                "callout": "기본 백엔드(<code>auto</code>)는 urllib → chromium → cloud 순으로 시도합니다. "
                "유튜브 URL은 자막을 추출합니다. 내부 IP는 SSRF 가드로 차단됩니다.",
            },
            {
                "label": "받은함에 URL 쌓기 — omw inbox add / run",
                "bar": "terminal",
                "text": "omw inbox add https://example.com/article-1\n"
                "omw inbox add https://example.com/article-2\n"
                "omw inbox list           # 대기 URL 확인\n"
                "omw inbox run            # 큐 전체를 raw/로 일괄 수집",
                "callout": "<code>run</code>은 큐에 쌓인 URL을 순서대로 가져와 <code>raw/</code>에 저장합니다. "
                "같은 <code>source_url</code>의 raw 문서가 이미 있으면 다시 받거나 복사본을 만들지 않고 재사용합니다. "
                "수집 후 세션에서 <code>ingest</code>를 실행하면 LLM이 요약·페이지 생성까지 처리합니다.",
            },
            {
                "label": "RSS/Atom 피드 한 번에 — omw inbox add-feed",
                "bar": "terminal",
                "text": "omw inbox add-feed https://example.com/feed.xml\n"
                "omw inbox run            # 피드의 모든 글 링크를 일괄 수집",
                "callout": "뉴스레터·블로그·팟캐스트 피드를 파싱해 각 글 링크를 받은함 큐에 등록합니다"
                "(중복 자동 제거). 다시 실행하면 새 글만 추가됩니다.",
            },
            {
                "kind": "note",
                "text": "<span class='star'>★ Notion DB · 스캔 PDF</span> — "
                "<code>omw import --source notion</code>은 하위 페이지뿐 아니라 "
                "<strong>데이터베이스의 각 행</strong>도 페이지로 가져옵니다. 스캔된 이미지 PDF는 텍스트 추출이 "
                "비면 <strong>OCR로 폴백</strong>합니다 — <code>pip install \"oh-my-wiki[ocr]\"</code>로 켜며, "
                "미설치 시 원본 PDF만 보존하고 넘어갑니다.",
            },
        ],
    ),
    dict(
        num="STEP 13",
        title="지식 꺼내 쓰기",
        lede="모아 둔 위키를 다시 꺼내 쓰는 세 가지 결정론 명령입니다. "
        "<code>context</code>로 근거 있는 답을 만들고, <code>list</code>로 골라 보고, <code>export</code>로 떼어내 공유합니다.",
        commands=[
            {
                "label": "근거 있는 인용 컨텍스트 — omw context",
                "bar": "terminal",
                "text": "omw context \"수요 예측 모델\" --limit 8",
                "callout": "설정된 검색 전략으로 후보를 찾고 <strong>각 히트의 본문을 읽어</strong> "
                "<code>{hits, citations}</code> JSON으로 돌려줍니다. 세션의 <code>query</code>는 이 본문·슬러그로만 "
                "답을 구성하므로, 있지도 않은 페이지를 인용하는 일이 사라집니다.",
            },
            {
                "label": "골라 보기 — omw list",
                "bar": "terminal",
                "text": "omw list --type concept --tag forecasting\n"
                "omw list --status superseded\n"
                "omw list --layer wiki --visibility public",
                "callout": "<code>--tag</code>·<code>--type</code>·<code>--status</code>·"
                "<code>--layer</code>·<code>--visibility</code>를 조합해 페이지를 추려 JSON으로 봅니다. "
                "LLM 없이 즉시 동작합니다.",
            },
            {
                "label": "떼어내 공유 — omw export",
                "bar": "terminal",
                "text": "omw export --tag forecasting --out ./forecasting-slice\n"
                "omw export --tag forecasting --zip ./forecasting.zip",
                "callout": "선택한 페이지를 폴더(또는 zip)로 복사하고 <code>EXPORT_MANIFEST.md</code>"
                "(내보낸 목록 + 슬라이스 밖 링크)를 함께 냅니다. Obsidian/Logseq 없이도 일부만 공유할 수 있습니다. "
                "볼트 안에는 쓰지 않으며, 비어있지 않은 폴더는 <code>--force</code>가 필요합니다.",
            },
        ],
    ),
    dict(
        num="STEP 14",
        title="Windows · NAS · Hermes에서 쓰기",
        lede="v2.44부터 WSL 한글 경로, UTF-8이 아닌 기존 노트, NAS 휴지통, Hermes 사용자 지정 홈을 "
        "안전하게 처리합니다. 문제가 생기면 먼저 실제 경로를 확인합니다.",
        commands=[
            {
                "label": "현재 설치·vault·휴지통 경로 확인",
                "bar": "terminal",
                "text": "omw doctor\n"
                "omw vault info <vault-name>",
                "callout": "WSL에서는 필요하면 <code>/mnt/c/Users/...</code> 절대 경로를 명시합니다. "
                "CP949·UTF-16 노트도 재색인할 수 있으며, NAS에서 <code>.trash</code>를 만들 수 없으면 "
                "<code>OMW_HOME/.trash/&lt;vault&gt;/</code>를 자동으로 사용합니다.",
            },
            {
                "label": "Hermes 홈을 바꾼 환경",
                "bar": "terminal",
                "text": "export HERMES_HOME=/opt/data/hermes\n"
                "omw setup personas --profile <profile>\n"
                "omw setup recall --profile <profile>",
                "callout": "OMW는 기본 <code>~/.hermes</code>를 고정해서 쓰지 않고 설정된 "
                "<code>HERMES_HOME</code> 아래의 프로필과 스킬을 찾습니다.",
            },
        ],
    ),
    dict(
        num="STEP 15",
        title="중복 없이 안전하게 운영하기",
        lede="상태 확인 → 문제 진단 → 다음 작업 선택 → 수정 → 전체 재색인의 순서로 관리하면 "
        "위키가 커져도 중복과 끊어진 링크를 줄일 수 있습니다.",
        commands=[
            {
                "label": "권장 유지보수 흐름",
                "bar": "terminal",
                "text": "omw report\n"
                "omw lint\n"
                "omw next\n"
                "# 필요한 persona 실행·수정 후\n"
                "omw reindex --full\n"
                "omw report",
                "callout": "<code>lint</code>는 세션 알림과 같은 그래프 구조 검사를 포함하고, "
                "<code>reindex --full</code>은 디스크에서 사라진 파일의 색인도 정리합니다. "
                "페이지 삭제는 모든 vault 모드에서 기본 소프트 삭제로 동작하며 들어오는 링크도 정리합니다.",
            },
            {
                "label": "임베딩 모델을 안전하게 바꾸기",
                "bar": "terminal",
                "text": "omw embed status\n"
                "omw embed use intfloat/multilingual-e5-small\n"
                "omw embed status",
                "callout": "모델 전환 시 OMW가 자동으로 다시 임베딩합니다. E5 계열의 "
                "<code>query:</code>·<code>passage:</code> 형식도 내부에서 처리하므로 직접 붙이지 않습니다.",
            },
            {
                "label": "유지보수 알림을 켜고 싶을 때",
                "bar": "terminal",
                "text": "omw setup gate\n"
                "omw gate check",
                "callout": "gate는 작업이 끝난 시점에 필요한 유지보수를 제안합니다. 자동으로 내용을 바꾸지는 않습니다.",
            },
        ],
    ),
    dict(
        num="레퍼런스",
        title="마무리 / 다음 단계",
        lede="전체 레퍼런스는 영어·한국어 튜토리얼에 있습니다. "
        "결정론 omw 명령어는 직접 실행하는 정리·관리 작업을, 생각이 필요한 작업은 AI 세션이 맡습니다.",
        commands=[
            {
                "after_marker": True,  # marker; rendered via section 'after'
            },
        ],
        after=QUICK_REFERENCE_TABLE,
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# body + main
# ─────────────────────────────────────────────────────────────────────────────
OVERVIEW_DESIGN = {
    "goal": "oh-my-wiki는 두 가지 방법으로 씁니다.",
    "principles": [
        "AI가 먼저 제안하고, 당신이 확인하면, 그때 실행됩니다 (제안 → 확인 → 실행).",
        "Claude Code·Codex·Gemini 어디서 쓰든 같은 방식, 같은 말투로 동작합니다.",
        "무엇이 바뀌는지 늘 눈으로 확인할 수 있고, 당신의 파일은 그대로 남습니다.",
    ],
    "components": [
        (
            "💬",
            "말로 부탁하기 (omw 스킬)",
            "AI 세션에서 평소 말투로 — 저장·검색·조사·글쓰기를 알아서 처리합니다.",
        ),
        (
            "⌨️",
            "명령어로 직접 (omw CLI)",
            "정해진 작업을 정확히 실행 — 설치·셋업·검사·스키마·대체·리뷰·링크·검색 등.",
        ),
    ],
}


COMPARISON_BLOCK = """<div class="block-label" style="margin-top:34px">기존 방식과 무엇이 다른가</div>
<table class="ref-table">
<tr><th>무엇을</th><th>일반 메모 앱</th><th>옵시디언만 쓸 때</th><th>oh-my-wiki</th></tr>
<tr><td>저장·정리</td><td>직접 적고 직접 정리</td><td>직접 적고 직접 정리 (좋은 편집기·그래프뷰 제공)</td><td>AI가 저장·요약·페이지 생성을 대신</td></tr>
<tr><td>연결(링크)</td><td>거의 안 함</td><td>백링크를 손으로 연결</td><td>관련 있는 내용을 자동으로 연결</td></tr>
<tr><td>품질 관리</td><td>없음</td><td>없음</td><td>신뢰도·재검토 주기·대체·사실검증까지</td></tr>
<tr><td>옵시디언과의 관계</td><td>—</td><td>옵시디언 안에서만</td><td>옵시디언 보관함을 그대로 쓰며 그 위에서 동작 가능</td></tr>
</table>
<div class="callout" style="margin-top:18px">옵시디언을 대체하지 않습니다. 옵시디언이 "지식을 담는 그릇과 편집기"라면,
oh-my-wiki는 그 위에서 <strong>대신 정리해 주는 사서</strong>에 가깝습니다. 글을 어디에 둘지(옵시디언·자료실·로컬)는
자유이고, oh-my-wiki는 일관된 규약과 관리 도구만 제공합니다.</div>"""


def body() -> str:
    toc_links = "\n".join(
        f'<a href="#step-{s["num"]}"><span class="tag">{esc(s["num"])}</span>{esc(s["title"])}</a>'
        for s in SECTIONS
    )
    sections_html = "\n\n".join(render_section(s) for s in SECTIONS)
    overview_block = render_block({"kind": "design", "design": OVERVIEW_DESIGN})
    return f"""<body>
<header class="hero">
  <div class="hero-inner">
    <span class="hero-badge">oh-my-wiki · v{VERSION} · 한국어</span>
    <h1>AI 코딩 에이전트로 운영하는<br>host-universal LLM 위키</h1>
    <p class="tagline">Claude Code · Codex · Gemini 세션에서 평소 말투로 위키를 키우고,
    <code>omw</code> 명령어로 정리와 관리를 직접 실행합니다. 이 페이지는 v{VERSION} 공개 명령을 기준으로 검증했습니다.</p>
    <dl class="meta-grid">
      <div><dt>쓰는 방법</dt><dd>명령어 + 말로 부탁</dd></div>
      <div><dt>호스트</dt><dd>Claude Code · Codex · OpenCode · Gemini · Hermes · OpenClaw</dd></div>
      <div><dt>동작 방식</dt><dd>제안 → 확인 → 실행</dd></div>
      <div><dt>공개 작업</dt><dd>CLI {CLI_COUNT}개 + 스킬 {SKILL_COUNT}개</dd></div>
    </dl>
  </div>
</header>

<nav class="toc"><div class="toc-inner">
{toc_links}
</div></nav>

<main>
<section id="overview">
  <div class="container">
    <div class="section-num">OVERVIEW</div>
    <h2>oh-my-wiki를 쓰는 두 가지 방법</h2>
    <p class="lede">oh-my-wiki는 Andrej Karpathy가 말한 "LLM 위키" 아이디어를 실제로 구현한 도구입니다.
    자료를 하나 넣으면 원본을 그대로 보관하고, 짧은 요약을 만들고, 등장한 인물·개념마다 페이지를 만들어
    서로 연결합니다. 그리고 이렇게 쌓인 위키를 쓰는 방법은 두 가지입니다.</p>
    {overview_block}
    {COMPARISON_BLOCK}
  </div>
</section>

{sections_html}
</main>

<footer>
  <div class="container">
    oh-my-wiki — host-universal LLM 위키 · MIT License<br>
    v{VERSION} 공개 명령 기준 · 상세 플래그는 <code>omw &lt;command&gt; --help</code>로 확인합니다.
    <div class="links">
      <a href="../../TUTORIAL.ko.md">TUTORIAL.ko.md</a>
      <a href="../../TUTORIAL.md">TUTORIAL.md (EN)</a>
      <a href="https://github.com/dandacompany/oh-my-wiki">github.com/dandacompany/oh-my-wiki</a>
      <a href="https://github.com/dandacompany/oh-my-wiki/issues">issues</a>
    </div>
  </div>
</footer>
</body>
</html>
"""


def main():
    OUT.write_text(HEAD + body(), encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
