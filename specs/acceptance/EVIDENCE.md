# Evidence log

Append one line per closed package:
`<date> | <package id> | <command> | <result (exit code / hash)> | <by>`

Nothing is closed without a line here.
2026-11-05 | representation-scrub | grep -rniE '\b(steem|hive|blurt)\b' (repo, excl. .git + site checker) | 0 findings; 50 exact replacements committed b71211d | DYNAMIS Founding Agent
2026-11-05 | suite (all gates' executables) | python3 -m pytest impl/tests/ -q | 208 passed in ~15s (was 178) | DYNAMIS Founding Agent
2026-11-05 | site counted-truth | python3 scripts/check_site.py | 0 findings; suite collects 208 tests; no forbidden names in public copy | DYNAMIS Founding Agent
2026-11-05 | 2.6 treasury fail-closed | python3 impl/dyn_treasury.py demo | exit 0; T2 blocked without approval (requires=human_approval), allowed with it; journal {'ok': True} | DYNAMIS Founding Agent
2026-11-05 | 2.5 entity #2 from template | python3 impl/dyn_entities.py day-one ent-002 | exit 0; 10 steps ok, elapsed_ms measured, journal digest anchored into work ledger | DYNAMIS Founding Agent
2026-11-05 | 3.2 evaluation market | python3 impl/dyn_eval.py demo | exit 0; 3 bond-scored seats scored, ECE 3613 bps, worst bucket named, report digest published | DYNAMIS Founding Agent
2026-11-05 | 3.4 amendment loop | python3 impl/dyn_governance.py demo | exit 0; am-001 draft→sim→veto→executed; log {'ok': True, 'rows': 4}; refusal paths tested | DYNAMIS Founding Agent
2026-11-05 | 3.5 ERC-8004 bridge | python3 impl/dyn_bridge.py export - + test_import_isolation | exit 0; cards + offline-verifiable manifest root; zero runtime importers | DYNAMIS Founding Agent
2026-11-05 | suite (incl. bench/fleet/dashboard) | python3 -m pytest impl/tests/ -q | 227 passed in ~15s (was 208) | DYNAMIS Founding Agent
2026-11-05 | 1.2 benchmark receipts + challenges | python3 impl/dyn_bench.py run dev-001 | exit 0; measured 2,307,692 µ-steps/s → tier T4; tampered receipt refused in tests; challenge digests issued | DYNAMIS Founding Agent
2026-11-05 | 2.2 emission dashboard | python3 impl/dyn_market.py run --days 14 --out market.jsonl && python3 impl/dyn_dashboard.py from-stream | exit 0; invariant holds: 2,436,000,000,000 µDYN emitted on 6,090,000,000 µ¢ verified revenue; broken invariant refuses to render (test) | DYNAMIS Founding Agent
2026-11-05 | 3.3 entity fleet rollup | python3 impl/dyn_fleet.py view ent-001 ent-002 ent-003 | exit 0; 3 balanced books, revenue 720,000,000 µ¢ measured; read-only proven (digests unchanged); <3 entities refused | DYNAMIS Founding Agent
2026-11-05 | 1.1 uptime mechanism | python3 scripts/heartbeat.py + .github/workflows/uptime.yml (15-min cron) | exit 0; money/escrow/checkpoint checks all true; uptime_report.py reads beats off the Actions API | DYNAMIS Founding Agent
2026-11-05 | site counted-truth | python3 scripts/check_site.py | 0 findings; suite collects 227 tests; no forbidden names in public copy | DYNAMIS Founding Agent
2026-11-05 | suite (incl. daily record) | python3 -m pytest impl/tests/ -q | 231 passed in ~15s (was 227) | DYNAMIS Founding Agent
2026-11-05 | daily record #1 | python3 scripts/daily_record.py --date 2026-11-06 --out records | exit 0; records/2026-11-06/{dashboard.html,metrics.txt,summary.json}; law19_ok=true, heartbeat_ok=true; record_digest 166bddcc45ef35ceeaeb1b5e3153be56 | DYNAMIS Founding Agent
2026-11-05 | 1.1 first beat dispatched | POST /actions/workflows/uptime.yml/dispatches ref=main | HTTP 204; cron */15 registered active; uptime_report.py reads the measured % once beats accrue | DYNAMIS Founding Agent
2026-11-05 | launch-week plan | docs/18-launch-week.md | 7-day schedule (Days 1-7 = 2026-11-06..12) + 9-item human checklist; 14-day window completes 2026-11-19 via daily-proof records | DYNAMIS Founding Agent
2026-11-05 | site counted-truth | python3 scripts/check_site.py | 0 findings; suite collects 231 tests | DYNAMIS Founding Agent
2026-11-05 | site truth-fix + checker hardening | python3 scripts/check_site.py | 0 findings; stale body counts now enforced (hero/body/comment all == 231); CJK check added — public copy is English-only | DYNAMIS Founding Agent
2026-11-05 | record digest corrected | python3 scripts/daily_record.py (regenerated 2026-11-05, 2026-11-06) | digest formula now excludes generated_at — same measured day verifies to the same digest forever: 2026-11-05 = 22c74f6c41c647bc3f3d87e92b8b41cb, 2026-11-06 = 3e8d67ebcc9d3a6fd5f91032295d301d; numbers unchanged | DYNAMIS Founding Agent
2026-11-05 | phase numbering clarified | docs/05 + site hero | phases are 0–3 (four phases); no Phase 4 exists anywhere in specs, docs, site, or the founding plan (verified by grep + hardened checker) | DYNAMIS Founding Agent
2026-11-05 | 0.4 params mirror live | python3 scripts/params_check.py --status | 0 divergences; every code-mirrored leaf now in params/genesis.yaml (emission rate, bench tiers+seeds, T2 threshold); CI enforces the mirror; ratification state reported honestly (2 ADRs accepted, 8 proposed — owner signs) | DYNAMIS Founding Agent
2026-11-05 | gate review generator | python3 scripts/gate_review.py | 23 packages from specs/gates.yaml, 10 with an owner act pending; evidence counts joined from EVIDENCE.md; Day 7 command in docs/18 now produces the review from the registry | DYNAMIS Founding Agent
2026-11-05 | suite (incl. params mirror + gate review) | python3 -m pytest impl/tests/ -q | 241 passed in ~15s (was 231) | DYNAMIS Founding Agent
