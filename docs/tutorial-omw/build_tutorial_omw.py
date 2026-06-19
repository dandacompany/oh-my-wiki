#!/usr/bin/env python3
"""Self-contained static HTML tutorial builder for oh-my-wiki (Korean, v3 focused showcase).

Single-file: HEAD (full <head> + <style>), esc(), render_section(), SECTIONS, body(), main().
All command blocks and outputs are copied verbatim from TUTORIAL.ko.md (accuracy-reviewed v3).
Personal OMW_HOME paths are shown as ~/.omw.
"""
import html
import pathlib

BASE = pathlib.Path(__file__).resolve().parent
OUT = BASE / "tutorial-omw.html"

# ─────────────────────────────────────────────────────────────────────────────
# HEAD — full <head> + <style> (sand / stone / moss earth palette)
# ─────────────────────────────────────────────────────────────────────────────
HEAD = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>oh-my-wiki v3 — 따라 하는 위키 셋업</title>
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
}
</style>
</head>
"""


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
                "label": "PATH A — Skills CLI (Claude Code 권장)",
                "bar": "bash",
                "text": "skills add dandacompany/oh-my-wiki@oh-my-wiki -g -y --copy -a claude-code",
                "callout": "스킬을 <code>~/.claude/skills/</code>에 설치하고 "
                "<code>oh-my-wiki</code>와 단축 별칭 <code>omw</code> 스킬 이름을 함께 등록합니다.",
            },
            {
                "label": "PATH B — Claude Code 플러그인 마켓플레이스",
                "bar": "claude code",
                "text": "/plugin marketplace add dandacompany/oh-my-wiki\n"
                "/plugin install oh-my-wiki@oh-my-wiki-marketplace",
                "callout": "이후 업데이트는 "
                "<code>/plugin marketplace update oh-my-wiki-marketplace</code>로 진행합니다.",
            },
            {
                "label": "PATH C — git clone + install script (Codex CLI · 개발자)",
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
        lede="다섯 가지 wiki-maintenance persona를 Claude Code / Codex / Gemini 세션에서 자연어로 호출합니다. "
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
                "label": "Curator — in your Claude session, say:",
                "bar": "ai session",
                "text": "curate my wiki — what pages are most in need of attention?",
                "callout": "공백, 고립 페이지, 구조적 취약점을 검토하고 유지 관리 계획을 제안합니다(세션 내).",
            },
            {
                "label": "Consistency-checker / Terminology-manager — in your Claude session, say:",
                "bar": "ai session",
                "text": "check for contradictions\n"
                "build a glossary for my vault",
                "callout": "전체 일관성 검사를 실행합니다. 모순, 용어 표류, 오래된 주장을 점검합니다.",
            },
            {
                "kind": "note",
                "text": "<span class='star'>★ 공통 모델</span> — "
                "모든 persona는 <strong>제안 → 확인 → 실행</strong>을 따릅니다. "
                "파일을 읽고, 제안 초안을 작성하고, 무엇이 변경될지 보여준 다음 작성합니다. "
                "전체 목록(wiki-librarian·curator·fact-checker·consistency-checker·terminology-manager)은 아래 레퍼런스에 있습니다.",
            },
        ],
    ),
    dict(
        num="STEP 10",
        title="프롬프트별 recall",
        lede="물어보는 순간 AI 에이전트가 활성 위키를 자동으로 참고하게 만드는 기능입니다. "
        "<code>omw find</code>를 직접 실행하지 않아도, 프롬프트마다 관련 페이지를 찾아 답변의 근거로 끌어옵니다. "
        "Claude Code · Codex · Gemini CLI 어디서나 동일하게 동작합니다(엔진 하나, 호스트별로 번역).",
        commands=[
            {
                "label": "recall 켜기 — omw setup recall",
                "bar": "terminal",
                "text": "omw setup recall",
                "callout": "<code>omw setup</code> 마법사의 한 섹션이기도 합니다. 모드를 설정하고, "
                "<code>CLAUDE.md</code>·<code>AGENTS.md</code>·<code>GEMINI.md</code>에 안내 블록을 주입하며, "
                "각 호스트의 네이티브 훅(<strong>SessionStart + UserPromptSubmit</strong>)을 "
                "Claude Code·Codex·Gemini CLI에 연결합니다.",
            },
            {
                "label": "설정 두 축 — recall.mode (언제) · recall.strategy (어떻게)",
                "bar": "config",
                "text": "recall.mode      auto       # 프롬프트마다 검색 → <omw-recall> 블록 주입\n"
                "                 advisory   # 훅은 권유만, 세션 내 에이전트가 직접 omw find (추가 비용 없음)\n"
                "                 off\n\n"
                "recall.strategy  fts        # 키워드 + 한국어 조사 정규화 (현재 구현)\n"
                "                 embedding  # (예정)\n"
                "                 hybrid     # (예정)\n"
                "                 llm        # (예정, 출시 전까지 fts로 폴백 — 지금도 선택 가능)",
                "callout": "<code>mode</code>는 <strong>언제</strong> 위키를 참고할지, "
                "<code>strategy</code>는 <strong>어떻게</strong> 후보를 찾을지를 정합니다. "
                "<code>auto</code>는 매 프롬프트를 검색하고, <code>advisory</code>는 세션 내 에이전트가 "
                "스스로 <code>omw find</code>를 실행하도록 권유만 합니다.",
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
                "recall은 좋은 <strong>title·tags·summary</strong> frontmatter에서 나옵니다. "
                "FTS는 본문이 아니라 이 메타필드로 순위를 매기기 때문입니다. "
                "<code>autoresearch</code>는 summary를 자동으로 채워 주므로 recall 정확도를 높여 줍니다.",
            },
        ],
    ),
    dict(
        num="STEP 11",
        title="Obsidian · Logseq에서 열기",
        lede="<code>omw setup viewer</code>로 기본 뷰어를 지정하고, "
        "<code>omw view</code>로 활성 vault·페이지·검색 결과를 URI 스킴으로 바로 엽니다. "
        "플러그인 설치 없이 동작합니다.",
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
                "수집 후 세션에서 <code>ingest</code>를 실행하면 LLM이 요약·페이지 생성까지 처리합니다.",
            },
        ],
    ),
    dict(
        num="레퍼런스",
        title="마무리 / 다음 단계",
        lede="전체 레퍼런스는 영어·한국어 튜토리얼에 있습니다. "
        "17개 omw 명령어는 직접 실행하는 정리·관리 작업을, 생각이 필요한 작업은 AI 세션이 맡습니다.",
        commands=[
            {
                "after_marker": True,  # marker; rendered via section 'after'
            },
        ],
        after="""<table class="ref-table">
<tr><th>서브커맨드</th><th>한 줄 설명</th></tr>
<tr><td><code>omw status</code></td><td>레지스트리 상태 표시: vault 수, 활성 vault, needs 코드</td></tr>
<tr><td><code>omw vault</code></td><td>Vault 관리: create · list · use · forget</td></tr>
<tr><td><code>omw lint</code></td><td>위키 건강 검사 (frontmatter + 링크 + 누락 파일)</td></tr>
<tr><td><code>omw search</code></td><td>설정된 외부 provider를 통한 웹 검색 (brave/tavily/exa/…)</td></tr>
<tr><td><code>omw serve</code></td><td>로컬 읽기 전용 HTTP 쿼리 API 시작 (포트 8765)</td></tr>
<tr><td><code>omw schema</code></td><td>페이지 타입 스키마 표시: list · show &lt;type&gt;</td></tr>
<tr><td><code>omw supersede</code></td><td>페이지를 status: superseded + superseded_by: &lt;slug&gt;로 표시</td></tr>
<tr><td><code>omw review</code></td><td>간격 반복 대기열: due · done</td></tr>
<tr><td><code>omw links</code></td><td>엔티티 자동 링크: suggest · link</td></tr>
<tr><td><code>omw fields</code></td><td>페이지의 frontmatter + 인라인 key:: value 필드 표시</td></tr>
<tr><td><code>omw import</code></td><td>폴더 / Obsidian vault / Notion export 가져오기</td></tr>
<tr><td><code>omw setup</code></td><td>대화형 마법사: vault · hosts · search · serve · personas · import · viewer · agents · recall</td></tr>
<tr><td><code>omw doctor</code></td><td>omw 설정 + 설치 건강 상태 검증</td></tr>
<tr><td><code>omw view</code></td><td>활성 vault·페이지·검색을 Obsidian/Logseq URI 스킴으로 열기</td></tr>
<tr><td><code>omw visibility</code></td><td>페이지 공개 여부 조회(get) · 설정(set public|private)</td></tr>
<tr><td><code>omw inbox</code></td><td>URL 큐 관리: add · list · remove · run(일괄 수집)</td></tr>
<tr><td><code>omw fetch</code></td><td>URL 하나를 raw/로 즉시 수집 (urllib→chromium→cloud 캐스케이드)</td></tr>
</table>
<div class="callout" style="margin-top:24px">
추론 작업(<code>ingest</code> · <code>query</code> · <code>find</code> · <code>open</code> · <code>edit</code> ·
<code>move</code> · <code>delete</code> · <code>autoresearch</code> · <code>persona-factcheck</code> ·
<code>persona-consistency</code> · <code>persona-terminology</code>)은 <strong>Claude / Codex / Gemini 세션</strong>에서 자연어로 사용합니다.
전체 레퍼런스: <a href="../../TUTORIAL.md">TUTORIAL.md (EN)</a> ·
<a href="../../TUTORIAL.ko.md">TUTORIAL.ko.md (KO)</a>.
</div>""",
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
    <span class="hero-badge">oh-my-wiki · v3 · 한국어</span>
    <h1>AI 코딩 에이전트로 운영하는<br>host-universal LLM 위키</h1>
    <p class="tagline">Claude Code · Codex · Gemini 세션에서 평소 말투로 위키를 키우고,
    <code>omw</code> 명령어로 정리와 관리를 직접 실행합니다. 모든 명령과 출력은 실제 v3 실행 결과 그대로입니다.</p>
    <dl class="meta-grid">
      <div><dt>쓰는 방법</dt><dd>명령어 + 말로 부탁</dd></div>
      <div><dt>호스트</dt><dd>Claude Code · Codex · Gemini</dd></div>
      <div><dt>동작 방식</dt><dd>제안 → 확인 → 실행</dd></div>
      <div><dt>CLI 명령어</dt><dd>17개</dd></div>
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
    모든 커맨드 블록과 출력은 v3 CLI 실행 결과(TUTORIAL.ko.md)에서 가져왔습니다.
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
