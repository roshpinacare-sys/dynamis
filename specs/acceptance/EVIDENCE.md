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
