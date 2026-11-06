# Discovery handshake — external instance, 2026-11-06 (docs/18 Day 6)

**Measured at HEAD e4e3f0e, live surfaces at
https://roshpinacare-sys.github.io/dynamis/discovery/ — bundle root `b86f43ef14657384bababc490bcc9afe`.**

The second agent instance shares nothing with this repo: no clone, no imports, no
state. It holds only the published URLs and reimplements the canonical rule stated
in the manifest's own `verify` line (sha256 over canonical JSON: sorted keys, no
whitespace, non-ASCII kept, UTF-8; truncated to 32 hex). Stdlib only. Driver source
sha256[:16] `3f440345a8c4d805`; replay: fetch each artifact, recompute, compare — the
transcript below is the driver's complete output.

```
- discover manifest: OK — bundle=discovery-surfaces/1, root=b86f43ef14657384bababc490bcc9afe
- artifact a2a-agent-card.json: OK — digest recomputes
- artifact erc8004-cards.json: OK — digest recomputes
- artifact schemas/claim.schema.json: OK — digest recomputes
- artifact schemas/job.schema.json: OK — digest recomputes
- artifact schemas/post.schema.json: OK — digest recomputes
- artifact schemas/receipt.schema.json: OK — digest recomputes
- artifact skills.json: OK — digest recomputes
- bundle root: OK — recomputed b86f43ef14657384bababc490bcc9afe
- inner ERC-8004 root: OK — 2 card(s), root 0e45ccfe4a8ccad35e862e9e9c8beaca
- card agent-alpha: OK — card digest recomputes
- card agent-beta: OK — card digest recomputes
- skill buy_job holders: OK — capability ['work.escrow'], holders ['agent-beta']
- skill settle_by_evidence holders: OK — capability ['verify.classB', 'verify.classC'], holders ['agent-alpha', 'agent-beta']
- skill publish_receipt holders: OK — capability ['post.dyn.v1'], holders ['agent-alpha']
- A2A skills == packaged skills: OK — 3 skill(s)
- envelope has job_id: OK
- envelope has entity_id: OK
- envelope has spec: OK
- envelope has escrow_usds_muc: OK
- envelope has deadline_day: OK
- envelope has verification_class: OK
- envelope has revenue_ref: OK
- envelope ids match the published id pattern: OK
- envelope escrow is an integer muc: OK
- envelope class in the published enum: OK
- envelope has no additional properties: OK
- handshake complete: OK — job envelope for agent-beta (card 44137715b6de9d7af5a7f9a2570b4961) is valid against the published schema — ready to POST /jobs when the persistent host serves the rail

DISCOVERY GREEN — discovered, verified, handshaken from the published surfaces alone
```

The live paid round-trip (`POST /jobs` over the public internet) still needs the
persistent host serving the rail — the envelope is built, validated, and waiting.
