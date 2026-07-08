# `synthesis` — weave a topic/cluster into a synthesis page

**Mode:** wiki

Proactive, cluster-driven counterpart of `query`'s "file as synthesis" step: take a
topic (or a graph cluster) and combine its structured pages into one
`wiki/syntheses/<slug>.md` page (schema `synthesis`: `synthesizes` list + `## Sources`).

## Preconditions

Active wiki-mode vault. There should be structured pages to weave — run
`omw connections` first to surface clusters if the topic is unspecified.

## Flow

1. **Take the topic/cluster** from the user (the `topic` arg). If absent, run
   `omw connections` and offer the top cluster(s).

2. **Gather the member pages.** Use `omw context "<topic>"` (cited retrieval) and/or
   `omw connections` to collect the relevant structured pages + their citations.

3. **Synthesize the prose.** Weave the members into standalone narrative — draw
   relationships, agreements, contradictions across sources. Do NOT invent facts;
   ground every claim in a member page. Keep a running list of source relpaths.

4. **Propose, then confirm** (never write silently). Show the draft + the source list.
   Ask: "File this synthesis page? [Yes / No]".

5. **On Yes, write it** (reuses `query.write_synthesis`):

   ```bash
   python3 -c "
   from scripts.paths import registry_path
   from scripts import query, ingest, registry
   db = registry_path()
   vault = registry.get_active(db)
   rel = query.write_synthesis(
       db, vault_id=vault['id'],
       title='<synthesis title>',
       body='<synthesized prose>',
       citations=['<member rel1>', '<member rel2>'],
       tags=['<t1>','<t2>'],
       date_str='<YYYY-MM-DD>',
   )
   ingest.update_index(db, vault_id=vault['id'],
       entries=[('syntheses', '<slug>', '<oneliner>')])
   ingest.append_log(db, vault_id=vault['id'],
       op='synthesis', title='<synthesis title>', date_str='<YYYY-MM-DD>')
   print(rel)
   "
   ```

## After

Run `omw next --after synthesis --json` and offer the next lifecycle step (lint) via
the host's native ask tool — safe default: stop.
