# omw connections — surface surprising connections

When the user asks for connection insight ("의외의 연결점", "어떤 주제들이 이어지나",
"connections", "what links my topics") run the deterministic detector and narrate it.

1. Run `omw connections` (add `--min-bridge-score N` to cut noise on dense vaults).
2. Read the JSON: `communities` (clusters), `bridges` (edges joining two communities —
   the surprising links), `hubs` (pages touching ≥2 communities), `modularity`.
3. If `communities` is empty or length 1 → tell the user the link graph is still too
   sparse for connection insight; suggest adding more pages/cross-links. Stop.
4. Otherwise narrate, grounded ONLY in the JSON:
   - Top bridges: "주제 A(커뮤니티 0)와 주제 Z(커뮤니티 3)가 의외로 연결됩니다 — <두 페이지>."
     Open or cite each endpoint's page (include its citations).
   - Top hubs: "페이지 H는 군집 0·2·3을 잇는 허브입니다."
   - Do NOT invent links absent from the report.
5. Optionally offer a follow-up: draft a synthesis page bridging two communities
   (that is a separate `ingest`/edit action, not part of this command).
