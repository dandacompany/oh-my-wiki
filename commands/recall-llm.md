# omw recall (llm strategy) — agent-delegated retrieval

When `recall.strategy=llm`, the recall hook does NOT search for you; it emits a short
`<omw-recall>` instruction. Follow the procedure for the active submode.

## route — choose how to search

1. Judge the query: lexical (proper nouns, exact terms, code identifiers) → keyword search;
   conceptual (synonyms, ideas, "how/why") → semantic search.
2. Run `omw find "<핵심 명사>"` (keyword) or, for conceptual queries, search with the
   semantic angle in mind. Use the configured deterministic backends as needed.
3. Ground the answer in what you find; cite the page's citations. If irrelevant, ignore.

## generative — read and filter

1. Pull candidates: `omw find "<핵심 명사>"`.
2. Open the candidate pages and READ them; keep only the ones genuinely relevant to the
   question (do not trust snippet/keyword matches).
3. Answer from the kept pages, citing their citations. If nothing is truly relevant, say
   "위키에 해당 근거가 없습니다" rather than guessing.

## Standing principles

- The wiki is the primary source; prefer it over general knowledge for project/domain facts.
- No grounded evidence → say so; never fabricate a citation.
