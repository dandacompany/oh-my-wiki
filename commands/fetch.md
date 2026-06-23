# fetch

Pull one URL into `raw/`. **Try your own built-in fetch/read first** (the host
agent's native web fetch). Only if that is blocked, empty, or unavailable, fall
back to `omw fetch <url>` — which cascades urllib → chromium → cloud scrape.

## When to invoke

- "fetch this url", "url 가져와", "페이지 가져와"
- after `omw search` returns target URLs to collect

## Procedure

1. Prefer your native fetch for the URL. If you get clean readable content, save it.
2. If native fetch fails/returns empty/is blocked, run `omw fetch <url>`
   (add `--backend chromium` for SPA pages, `--backend cloud` for hard blocks).
3. Confirm the saved `raw/<...>.md` has real body text (not just a title).

## Scout before you fetch

Before fetching an unknown topic, scout target URLs with `omw search "<query>"`
(it auto-falls back across keyed providers) and feed the returned `url`s here.
