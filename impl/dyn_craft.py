#!/usr/bin/env python3
"""dyn.craft.v1 — the craft-anything loop, where it pays.

Pattern credit and deep study: `storytold/craft-anything` (the ArtCraft engine:
Study → Build → Check → Ready on any target, refinement rounds with a
good-enough likeness bar, claims judged one by one, missing evidence never
counts as alike, evidence records whose ids are content hashes). DYNAMIS runs
the same loop where it pays: a buyer points a craft job at a target and says
what they want; a worker studies it, builds a version, and the check measures
how alike the build is — settlement moves money only on evidence.

The craft-anything contract, carried over:
  - a job is a folder: craft.json (manifest: request, target, status, checks
    history), capture/ (study facts + plain-words notes), app/ (the build),
    checks/round-N/ (each comparison), inbox/ (open questions), evidence/,
    post/;
  - a CheckResult reads: passed, similarity (0..=100), claims (each judged on
    its own — one failing claim blocks readiness however alike the rest looks),
    unknowns (what the check meant to compare but couldn't — missing evidence
    never counts as alike), note (plain words for people; decisions read
    fields, never prose);
  - likeness: Dice over word counts, 0..=100, two empty outputs are alike;
  - evidence records: id = `ev_` + SHA-256 of the canonical JSON of every
    field except display-only ones, `verify()` recomputes it, and
    `carries_target_content` marks records whose result embeds bytes from the
    target — readers treat those as data from an untrusted artifact.

What DYNAMIS adds, and why: the loop is an economy. The escrow is named in the
manifest and moves only through the protocol machine (AgentKit) — a build that
never passes the check is refunded with zero fees and zero emission (Law 19),
and a settled build publishes its proof as a dyn.post.v1 post whose embeds
carry the shipped bytes.

Kinds in v1 (each with its honest limitations on the record):
  - `web`  — study fetches the page (status, headers, title, headings, links,
    visible text); check compares the rebuilt `app/index.html` structurally.
    No browser runs: no screenshots, no JavaScript — a client-rendered page
    studies as its HTML source says.
  - `file` — study inspects a file (hash, size, type sniff, structure); the
    build is a program that reports the same facts; check runs it and compares
    claim by claim.

Stdlib only (ADR-0007).
"""
from __future__ import annotations

import argparse
import hashlib
import html as html_mod
import json
import re
import subprocess
import sys
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dynamis_core import Claim as EscrowClaim, EmissionLedger, object_hash, usds
from dyn_ledger import WorkLedger
from dyn_post import parse_post, to_wire

PROTOCOL = "dyn.craft.v1"
STEPS = ("study", "build", "check", "ready")
WORD_ALIKE = 80.0          # a text-likeness claim holds at this Dice score
LINK_RATIO_TOLERANCE = 0.25
DEFAULT_MAX_ROUNDS = 6
DEFAULT_GOOD_ENOUGH = 90.0
MAX_RUNTIME_S = 10
MAX_ROUTES = 4             # same-site pages study crawls, as the reference engine's max_pages


class CraftError(ValueError):
    """The loop refuses to continue. Fail-closed, with the reason on record."""


# --------------------------------------------------------------------------
# likeness: Dice over word counts, exactly as the reference engine scores it
# --------------------------------------------------------------------------
def words(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        counts[w] = counts.get(w, 0) + 1
    return counts


def alike(a: dict[str, int], b: dict[str, int]) -> float:
    """Dice over word counts, 0..=100; two empty outputs are alike."""
    total = sum(a.values()) + sum(b.values())
    if total == 0:
        return 100.0
    shared = sum(min(n, b.get(w, 0)) for w, n in a.items())
    return 200.0 * shared / total


# --------------------------------------------------------------------------
# evidence records: ev_ + content hash, verify(), untrusted-content flag
# --------------------------------------------------------------------------
_DISPLAY_ONLY = ("summary", "carries_target_content")


class Evidence:
    def __init__(self, *, operation: str, subject: dict, params: dict,
                 result: dict, summary: str, confidence: dict, authority: dict,
                 limitations: list[dict], coverage: dict,
                 carries_target_content: bool = False) -> None:
        self.operation = operation
        self.subject = subject
        self.params = params
        self.result = result
        self.summary = summary
        self.confidence = confidence
        self.authority = authority
        self.limitations = limitations
        self.coverage = coverage
        self.carries_target_content = carries_target_content
        self.id = "ev_" + object_hash(self._identity())[:63]

    def _identity(self) -> dict:
        subject = {k: v for k, v in self.subject.items() if k != "name"}
        return {"operation": self.operation, "subject": subject,
                "params": self.params, "result": self.result,
                "confidence": self.confidence, "authority": self.authority,
                "limitations": self.limitations, "coverage": self.coverage}

    def verify(self) -> bool:
        probe = Evidence(operation=self.operation, subject=self.subject,
                         params=self.params, result=self.result,
                         summary=self.summary, confidence=self.confidence,
                         authority=self.authority,
                         limitations=self.limitations, coverage=self.coverage,
                         carries_target_content=self.carries_target_content)
        return probe.id == self.id

    def to_dict(self) -> dict:
        return {"id": self.id, "operation": self.operation,
                "subject": self.subject, "params": self.params,
                "result": self.result, "summary": self.summary,
                "confidence": self.confidence, "authority": self.authority,
                "limitations": self.limitations, "coverage": self.coverage,
                "carries_target_content": self.carries_target_content}


def _ev_store(root: Path, ev: Evidence) -> str:
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    (root / "evidence" / f"{ev.id[:20]}.json").write_text(
        json.dumps(ev.to_dict(), indent=1, sort_keys=True) + "\n")
    return ev.id


# --------------------------------------------------------------------------
# the web parser: title, headings, links, visible text
# --------------------------------------------------------------------------
class _Page(HTMLParser):
    _SKIP = ("script", "style")

    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.headings: list[str] = []
        self.links: list[str] = []
        self.text: list[str] = []
        self._in_title = self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._SKIP:
            self._skip += 1
        if tag == "title":
            self._in_title += 1
        if re.fullmatch(r"h[1-6]", tag):
            self.headings.append("")
        if tag == "a":
            for k, v in attrs:
                if k == "href" and v:
                    self.links.append(v)

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        if tag == "title" and self._in_title:
            self._in_title -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif not self._skip:
            if self.headings and self.headings[-1] == "":
                self.headings[-1] = data.strip()
            else:
                self.text.append(data)


def parse_page(html_text: str) -> dict:
    p = _Page()
    p.feed(html_text)
    text = " ".join(t for t in (s.strip() for s in p.text) if t)
    return {"title": html_mod.unescape(p.title.strip()),
            "headings": [html_mod.unescape(h) for h in p.headings if h],
            "links": p.links, "text": text,
            "word_count": len(words(text))}


# --------------------------------------------------------------------------
# the craft job: a folder, exactly as the reference engine shapes it
# --------------------------------------------------------------------------
class CraftJob:
    """One craft job folder: study → build → check → (refine) → ready."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.manifest_path = self.root / "craft.json"
        self.manifest: dict = (json.loads(self.manifest_path.read_text())
                               if self.manifest_path.exists() else {})

    # ---------- lifecycle ----------
    def open(self, *, job_id: str, buyer: str, request: str, target_kind: str,
             target_ref: str, value_usds: int, ledger: WorkLedger, day: int,
             entity_id: str = "ent-001", stack: str = "python3 stdlib",
             max_rounds: int = DEFAULT_MAX_ROUNDS,
             good_enough: float = DEFAULT_GOOD_ENOUGH) -> dict:
        if self.manifest:
            raise CraftError(f"{self.root} is already a craft job ({self.manifest['job_id']})")
        if target_kind not in ("web", "file"):
            raise CraftError(f"unknown target kind {target_kind!r} — v1 studies web pages and files")
        if not request.strip():
            raise CraftError("the request is the person's words — it cannot be empty")
        if not 0 <= good_enough <= 100:
            raise CraftError("good_enough is a likeness bar in 0..=100")
        now = int(time.time() * 1000)
        self.manifest = {"version": 1, "protocol": PROTOCOL, "job_id": job_id,
                         "name": job_id, "request": request.strip(),
                         "target": {"kind": target_kind, "ref": target_ref},
                         "stack": stack, "buyer": buyer, "worker": None,
                         "status": "opened", "step": "study", "note": "opened; study next",
                         "escrow_usds_muc": usds(value_usds),
                         "verification_class": "B",
                         "deadline_day": day + 10,
                         "created_ms": now, "updated_ms": now,
                         "rounds": {"done": 0, "max": max_rounds},
                         "good_enough": good_enough,
                         "checks": [], "post": None}
        self._save()
        ledger.append(day=day, kind="open", job_id=job_id, agent=buyer,
                      escrow_usds_muc=self.manifest["escrow_usds_muc"],
                      target_kind=target_kind)
        return dict(self.manifest)

    # ---------- study: capture the target before the first build ----------
    def study(self, *, ledger: WorkLedger, day: int) -> dict:
        self._require(statuses=("opened",))
        target = self.manifest["target"]
        capture = self.root / "capture"
        capture.mkdir(parents=True, exist_ok=True)
        if target["kind"] == "web":
            facts, evs = self._study_web(target["ref"])
        else:
            facts, evs = self._study_file(Path(target["ref"]))
        (capture / "facts.json").write_text(
            json.dumps(facts, indent=1, sort_keys=True) + "\n")
        notes = ["# What study captured", "",
                 f"Target: {target['kind']} `{target['ref']}`.",
                 f"Request: {self.manifest['request']}", "",
                 "Facts are in `facts.json`; the evidence records behind each",
                 "answer carry their confidence, coverage and limitations.", ""]
        for ev in evs:
            notes.append(f"- {ev.summary} (`{ev.id[:20]}…`)")
        (capture / "README.md").write_text("\n".join(notes) + "\n")
        for ev in evs:
            _ev_store(self.root, ev)
        unknowns = [u for u in facts.get("unknowns", [])]
        for i, u in enumerate(unknowns, 1):
            self._ask(f"q-{i:03d}", u)
        self.manifest["status"] = "studied"
        self.manifest["step"] = "build"
        self.manifest["note"] = f"study captured {len(evs)} evidence record(s)"
        if unknowns:
            self.manifest["note"] += f"; {len(unknowns)} open question(s) in inbox/"
        qid = f"q-{len(unknowns) + 1:03d}"
        self._ask(qid, f"Approve the study and release the build? Escrow "
                       f"{self.manifest['escrow_usds_muc'] // 1_000_000} USDS; "
                       f"{len(evs)} evidence record(s), {len(unknowns)} open "
                       f"question(s). approve / deny.", kind="approval")
        self.manifest["note"] += f"; approval card open ({qid}) — the buyer decides before the build"
        self._save()
        ledger.append(day=day, kind="check", job_id=self.manifest["job_id"],
                      agent=self.manifest["buyer"], overall="STUDIED",
                      records=len(evs), unknowns=len(unknowns))
        return {"evidence": [ev.id for ev in evs], "unknowns": unknowns}

    def _study_web(self, url: str) -> tuple[dict, list[Evidence]]:
        req = urllib.request.Request(url, headers={"User-Agent": "dyn-craft-v1 (+protocol study)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read(2_000_000).decode("utf-8", "replace")
            status = r.status
            headers = {k: v for k, v in r.headers.items()
                       if k.lower() in ("content-type", "server", "content-length")}
        page = parse_page(body)
        site = urlparse(url).netloc
        same_site = sum(1 for h in page["links"]
                        if urlparse(urljoin(url, h)).netloc in ("", site))
        facts = {"kind": "web", "url": url, "status": status, "headers": headers,
                 "title": page["title"], "headings": page["headings"],
                 "link_count": len(page["links"]),
                 "same_site_links": same_site,
                 "text_words": page["word_count"], "text": page["text"][:20_000],
                 "routes": [], "unknowns": ["no browser ran: client-rendered content reads as its HTML source"]}
        ev = Evidence(operation="craft_web_capture", subject={"kind": "website", "name": url},
                      params={"url": url, "max_bytes": 2_000_000},
                      result={"status": status, "headers": headers,
                              "title": page["title"], "headings": page["headings"],
                              "link_count": len(page["links"]),
                              "same_site_links": same_site,
                              "word_count": page["word_count"]},
                      summary=f"Fetched {url}: HTTP {status}, title “{page['title']}”, "
                              f"{len(page['headings'])} headings, {len(page['links'])} links, "
                              f"{page['word_count']} words.",
                      confidence={"level": "high",
                                  "reason": "measured from the bytes the server returned"},
                      authority={"basis": "measured"},
                      limitations=[{"code": "no-browser",
                                    "message": "no JavaScript runs; a client-rendered page reads as its source"},
                                   {"code": "no-screenshots",
                                    "message": "likeness is structural, not pixel-level"}],
                      coverage={"basis": "single page", "bytes": len(body)},
                      carries_target_content=True)
        evs = [ev]
        routes = self._study_routes(url, page["links"], facts)
        if routes:
            (self.root / "capture" / "routes").mkdir(parents=True, exist_ok=True)
            for rt in routes:
                (self.root / "capture" / "routes" / f"{rt['slug']}.json").write_text(
                    json.dumps(rt, indent=1, sort_keys=True) + "\n")
            facts["routes"] = [{"path": rt["path"], "slug": rt["slug"]}
                               for rt in routes]
            evs.append(Evidence(
                operation="craft_web_routes", subject={"kind": "website", "name": url},
                params={"start": url, "max_routes": MAX_ROUTES},
                result={"routes": [{"path": rt["path"], "slug": rt["slug"],
                                    "title": rt.get("title", ""), "error": rt.get("error")}
                                   for rt in routes]},
                summary=f"Crawled {len(routes)} same-site route(s) from the start page, "
                        f"up to {MAX_ROUTES}, one level deep — same rules as the reference engine.",
                confidence={"level": "high", "reason": "each route fetched and parsed like the start page"},
                authority={"basis": "measured"},
                limitations=[{"code": "crawl-breadth",
                              "message": f"at most {MAX_ROUTES} same-site routes; deeper pages are not studied"},
                             {"code": "no-browser", "message": "no JavaScript runs"}],
                coverage={"basis": "sampled", "pages": 1 + len(routes)},
                carries_target_content=True))
        return facts, evs

    def _study_routes(self, start: str, links: list[str],
                      facts: dict) -> list[dict]:
        """The start page's other pages, up to MAX_ROUTES — the reference
        engine's pick_routes rules: same origin, no file links, no start path,
        deduped by normalized path, dash-slugs."""
        origin = f"{urlparse(start).scheme}://{urlparse(start).netloc.lower()}"
        start_path = urlparse(start).path.rstrip("/")
        picked: list[dict] = []
        for href in links:
            if len(picked) >= MAX_ROUTES:
                break
            absu = urljoin(start, href)
            u = urlparse(absu)
            if f"{u.scheme}://{u.netloc.lower()}" != origin:
                continue
            path = u.path or "/"
            last = path.rsplit("/", 1)[-1]
            if "." in last and not last.endswith((".html", ".htm")):
                continue
            if path.rstrip("/") == start_path:
                continue
            if any(r["path"].rstrip("/") == path.rstrip("/") for r in picked):
                continue
            slug = re.sub(r"[^a-z0-9]+", "-",
                          path.strip("/").lower()).strip("-")
            if not slug or any(r["slug"] == slug for r in picked):
                continue
            rt = {"url": f"{origin}{path}", "path": path, "slug": slug}
            try:
                with urllib.request.urlopen(urllib.request.Request(
                        rt["url"], headers={"User-Agent": "dyn-craft-v1 (+protocol study)"}),
                        timeout=20) as r:
                    rpage = parse_page(r.read(2_000_000).decode("utf-8", "replace"))
                rt.update({"title": rpage["title"], "headings": rpage["headings"],
                           "links": len(rpage["links"]),
                           "text": rpage["text"][:20_000],
                           "word_count": rpage["word_count"]})
            except Exception as exc:                  # a page that won't fetch is said, not hidden
                rt["error"] = str(exc)[:120]
                facts["unknowns"].append(
                    f"route {path} couldn't be fetched at study — it cannot be judged")
            picked.append(rt)
        return picked

    def _study_file(self, path: Path) -> tuple[dict, list[Evidence]]:
        if not path.is_file():
            raise CraftError(f"target {path} is not a file")
        raw = path.read_bytes()
        kind = "json" if raw[:1] in (b"{", b"[") else \
            ("text" if all(b in b"\t\n\r\x0c\x1f" or 32 <= b < 127 or b >= 128 for b in raw[:512]) else "binary")
        lines = raw.count(b"\n") + (0 if raw.endswith(b"\n") or not raw else 1)
        structure: dict = {}
        if kind == "json":
            try:
                data = json.loads(raw)
                structure = {"top_level_keys": sorted(data)[:64]
                             if isinstance(data, dict) else [],
                             "top_level_type": type(data).__name__}
                if isinstance(data, list):
                    structure["items"] = len(data)
            except json.JSONDecodeError as exc:
                structure = {"parse_error": str(exc)[:120]}
        facts = {"kind": "file", "path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                 "bytes": len(raw), "lines": lines, "type": kind,
                 "structure": structure,
                 "unknowns": ["a sniffed type is a guess, not a guarantee"]}
        ev = Evidence(operation="craft_file_inspect",
                      subject={"kind": "file", "name": path.name},
                      params={"path": str(path)},
                      result={"sha256": facts["sha256"], "bytes": len(raw),
                              "lines": lines, "type": kind, "structure": structure},
                      summary=f"Inspected {path.name}: {len(raw)} bytes, {lines} lines, "
                              f"type {kind}.",
                      confidence={"level": "high", "reason": "read the file in full"},
                      authority={"basis": "measured"},
                      limitations=[{"code": "type-sniff",
                                    "message": "the type comes from magic bytes and content shape"}],
                      coverage={"basis": "complete", "bytes": len(raw)},
                      carries_target_content=True)
        return facts, [ev]

    # ---------- build ----------
    def build(self, *, worker: str, files: dict[str, str],
              ledger: WorkLedger, day: int) -> dict:
        self._require(statuses=("studied", "checked_fail"))
        self._no_open_approval("the build")
        if self.manifest["status"] == "checked_fail":
            if self.manifest["rounds"]["done"] >= self.manifest["rounds"]["max"]:
                raise CraftError("refinement rounds exhausted — the loop refuses a further build")
            ledger.append(day=day, kind="refine", job_id=self.manifest["job_id"],
                          agent=worker, round=self.manifest["rounds"]["done"])
        if not files:
            raise CraftError("a build without files is not a build")
        app = self.root / "app"
        app.mkdir(parents=True, exist_ok=True)
        recorded = {}
        for name, content in files.items():
            if (not re.fullmatch(r"[A-Za-z0-9._/-]+", name) or ".." in name
                    or name.startswith("/") or name.endswith("/")):
                raise CraftError(f"file name {name!r} fails the name check")
            p = app / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            recorded[name] = {"sha256": hashlib.sha256(content.encode()).hexdigest(),
                              "bytes": p.stat().st_size}
        self.manifest["worker"] = worker
        self.manifest["status"] = "built"
        self.manifest["step"] = "check"
        self.manifest["note"] = f"build recorded: {len(files)} file(s)"
        self._save()
        ledger.append(day=day, kind="work", job_id=self.manifest["job_id"],
                      agent=worker, files=len(files),
                      sha256=object_hash(recorded))
        return recorded

    # ---------- check: measure how alike the build is ----------
    def check(self, *, ledger: WorkLedger, day: int) -> dict:
        self._require(statuses=("built", "checked_fail"))
        facts = json.loads((self.root / "capture" / "facts.json").read_text())
        round_n = self.manifest["rounds"]["done"] + 1
        if self.manifest["target"]["kind"] == "web":
            result = self._check_web(facts, round_n)
        else:
            result = self._check_file(facts, round_n)
        result["round"] = round_n
        result["at_ms"] = int(time.time() * 1000)
        result.setdefault("compared", True)
        # canonical wire is integers-only (ADR-0007): likeness rides as per-mille
        result["similarity_milli"] = int(round((result.pop("similarity", 0) or 0) * 10))
        out = self.root / "checks" / f"round-{round_n}"
        out.mkdir(parents=True, exist_ok=True)
        (out / "result.json").write_text(
            json.dumps(result, indent=1, sort_keys=True) + "\n")
        self.manifest["rounds"]["done"] = round_n
        self.manifest["checks"].append(result)
        if result["passed"]:
            self.manifest["status"] = "checked_pass"
            self.manifest["step"] = "ready"
            self.manifest["note"] = f"round {round_n}: {result['similarity_milli'] / 10:.0f}% alike, ready to settle"
        else:
            self.manifest["status"] = "checked_fail"
            self.manifest["note"] = f"round {round_n}: {result['note']}"
        self._save()
        ledger.append(day=day, kind="check", job_id=self.manifest["job_id"],
                      agent=self.manifest["worker"] or "unassigned",
                      round=round_n, overall="PASS" if result["passed"] else "FAIL",
                      similarity_milli=result["similarity_milli"],
                      failed_claims=[c["title"] for c in result["claims"] if not c["passed"]])
        return result

    def _check_web(self, facts: dict, round_n: int) -> dict:
        page_path = self.root / "app" / "index.html"
        unknowns: list[str] = []
        if not page_path.is_file():
            return {"check": "web-structure", "round": round_n, "passed": False,
                    "compared": False, "note": "no app/index.html to compare",
                    "claims": [], "unknowns": [], "artifacts": []}
        built = parse_page(page_path.read_text(encoding="utf-8", errors="replace"))
        score = alike(words(facts.get("text", "")), words(built["text"]))
        title_ok = facts.get("title", "").strip() == built["title"].strip()
        head_ok = all(any(h.strip().lower() == bh.strip().lower()
                          for bh in built["headings"])
                      for h in facts.get("headings", []))
        cap_links, built_links = facts.get("link_count", 0), len(built["links"])
        link_ok = (cap_links == 0 and built_links == 0) or (
            cap_links > 0 and built_links > 0
            and abs(built_links - cap_links) <= cap_links * LINK_RATIO_TOLERANCE)
        claims = [
            {"title": "its title matches the original", "passed": title_ok,
             "detail": "" if title_ok else
             f"original “{facts.get('title')}” vs build “{built['title']}”"},
            {"title": f"at least {WORD_ALIKE:.0f}% of the visible words match",
             "passed": score >= WORD_ALIKE,
             "detail": "" if score >= WORD_ALIKE else f"{score:.0f}%"},
            {"title": "every original heading appears in the build",
             "passed": head_ok,
             "detail": "" if head_ok else "missing: " + ", ".join(
                 h for h in facts.get("headings", [])
                 if not any(h.strip().lower() == bh.strip().lower() for bh in built["headings"]))},
            {"title": "its link count is close to the original's",
             "passed": link_ok,
             "detail": "" if link_ok else f"original {cap_links} links, build {built_links}"},
        ]
        if not facts.get("text"):
            unknowns.append("the original's visible text was never captured — likeness cannot be judged")
        # the studied routes, page by page — a page the build lacks is not alike
        routes = facts.get("routes", [])
        pages: list[dict] = []
        route_scores: list[float] = []
        for rt in routes:
            slug = rt["slug"]
            full = rt if "text" in rt else json.loads(
                (self.root / "capture" / "routes" / f"{slug}.json").read_text())
            if full.get("error") or not full.get("text"):
                pages.append({"name": rt["path"], "compared": False, "similarity_milli": 0})
                unknowns.append(f"{rt['path']} couldn't be fetched at study — it cannot be judged")
                continue
            bp = self.root / "app" / "routes" / f"{slug}.html"
            if not bp.is_file():
                pages.append({"name": rt["path"], "compared": False, "similarity_milli": 0})
                unknowns.append(f"{rt['path']} couldn't be compared — the build has no routes/{slug}.html")
                continue
            bpage = parse_page(bp.read_text(encoding="utf-8", errors="replace"))
            pscore = alike(words(full["text"]), words(bpage["text"]))
            pages.append({"name": rt["path"], "compared": True,
                          "similarity_milli": int(round(pscore * 10))})
            route_scores.append(pscore)
        route_claims: list[dict] = []
        if routes:
            missing = [p["name"] for p in pages if not p["compared"]]
            route_claims.append(
                {"title": "every studied page exists in the build", "passed": not missing,
                 "detail": "" if not missing else "missing: " + ", ".join(missing)})
            low = [f"{p['name']} ({p['similarity_milli'] / 10:.0f}%)"
                   for p in pages if p["compared"] and p["similarity_milli"] / 10 < WORD_ALIKE]
            route_claims.append(
                {"title": f"every studied page is at least {WORD_ALIKE:.0f}% alike",
                 "passed": not low, "detail": "" if not low else "low: " + ", ".join(low)})
        claims.extend(route_claims)
        scores = [score] + route_scores
        similarity = round(sum(scores) / len(scores), 1)
        hard_ok = title_ok and head_ok and link_ok and score >= WORD_ALIKE \
            and all(c["passed"] for c in route_claims)
        bar = self.manifest["good_enough"]
        passed = hard_ok and similarity >= bar and not unknowns
        note = f"{similarity:.0f}% alike" + (
            f" across {len(scores)} page(s)" if len(scores) > 1 else "") + ("" if passed else
            (" — below the good-enough bar" if hard_ok and similarity < bar
             else " — claims fail: " + ", ".join(c["title"] for c in claims if not c["passed"])))
        return {"check": "web-structure", "round": round_n, "passed": passed,
                "similarity": similarity, "note": note, "claims": claims,
                "unknowns": unknowns, "pages": pages,
                "artifacts": ["app/index.html"]}

    def _check_file(self, facts: dict, round_n: int) -> dict:
        program = self.root / "app" / "main.py"
        unknowns: list[str] = []
        if not program.is_file():
            return {"check": "app-runs", "round": round_n, "passed": False,
                    "compared": False, "note": "no app/main.py to run",
                    "claims": [], "unknowns": [], "artifacts": []}
        t0 = time.monotonic()
        proc = subprocess.run([sys.executable, str(program), facts["path"]],
                              capture_output=True, text=True, timeout=MAX_RUNTIME_S)
        runtime = time.monotonic() - t0
        runs_ok = proc.returncode == 0
        try:
            got = json.loads(proc.stdout)
        except json.JSONDecodeError:
            got = None
            unknowns.append("the build printed nothing parsable — its output cannot be compared")
        bytes_ok = bool(got) and got.get("bytes") == facts["bytes"]
        lines_ok = bool(got) and got.get("lines") == facts["lines"]
        type_ok = bool(got) and got.get("type") == facts["type"]
        sha_ok = bool(got) and got.get("sha256") == facts["sha256"]
        claims = [
            {"title": f"it runs under {MAX_RUNTIME_S}s and exits cleanly",
             "passed": runs_ok, "detail": "" if runs_ok else
             f"exit {proc.returncode}: {proc.stderr.strip()[-120:]}"},
            {"title": "it reports the same byte size", "passed": bytes_ok,
             "detail": "" if bytes_ok else "byte size differs"},
            {"title": "it reports the same line count", "passed": lines_ok,
             "detail": "" if lines_ok else "line count differs"},
            {"title": "it identifies the same type", "passed": type_ok,
             "detail": "" if type_ok else "type differs"},
            {"title": "it reports the same content hash", "passed": sha_ok,
             "detail": "" if sha_ok else "content hash differs"},
        ]
        score = alike(words(json.dumps(
            {k: facts[k] for k in ("sha256", "bytes", "lines", "type")},
            sort_keys=True)), words(proc.stdout)) if got else 0.0
        similarity = round(score, 1)
        hard_ok = all(c["passed"] for c in claims)
        bar = self.manifest["good_enough"]
        passed = hard_ok and similarity >= bar and not unknowns
        note = f"{similarity:.0f}% alike, {runtime:.2f}s" + ("" if passed else
               (" — below the good-enough bar" if hard_ok and similarity < bar
                else " — claims fail"))
        return {"check": "app-runs", "round": round_n, "passed": passed,
                "similarity": similarity, "note": note, "claims": claims,
                "unknowns": unknowns, "artifacts": ["app/main.py"]}

    # ---------- ready: the money, fail-closed on the evidence ----------
    def settle(self, *, ledger: WorkLedger, day: int, persona: str = "craft.worker",
               keyref: str = "hsm:kr-craft") -> dict:
        self._require(statuses=("checked_pass",))
        self._no_open_approval("settlement")
        last = self.manifest["checks"][-1]
        if not last["passed"]:
            raise CraftError("settle requires a passing check — the evidence on disk decides")
        if any(c for c in last["claims"] if not c["passed"]):
            raise CraftError("a claim that fails blocks settlement")
        if last["unknowns"]:
            raise CraftError("unknowns on the record block settlement — "
                             "missing evidence never counts as alike")
        from agent_kit import AgentKit, witness_verdict
        worker_id = self.manifest["worker"]
        led = EmissionLedger()
        entity = AgentKit("ent-001", "entity-rail", "hsm:kr-entity", role="entity")
        machine = entity.open_job(self.manifest["job_id"], "ent-001",
                                  {"task": "craft_rebuild", "target": self.manifest["target"]},
                                  self.manifest["escrow_usds_muc"],
                                  self.manifest["deadline_day"], f"env-{self.manifest['job_id']}")
        machine.fire("claim", worker=worker_id)
        receipt = object_hash({"checks": self.manifest["checks"],
                               "facts": object_hash(json.loads(
                                   (self.root / "capture" / "facts.json").read_text()))})
        claim = EscrowClaim(f"cl-{self.manifest['job_id']}-{worker_id}",
                            self.manifest["job_id"], worker_id,
                            (object_hash(last),), receipt, day)
        machine.fire("deliver", claim=claim)
        machine.fire("start_verify")
        witness_verdict(machine, n_workers=1, reexec_matches=True, seed=day)
        result = AgentKit(worker_id, persona, keyref,
                          stake_dyn_mu=2_500_000, day=day).settle(machine, led)
        self.manifest["status"] = "settled"
        self.manifest["note"] = (f"settled: payout {result['payout_muc']:,} µ¢, "
                                 f"emitted {result['emitted_dyn_mu']:,} DYN µ")
        self._save()
        ledger.append(day=day, kind="settle", job_id=self.manifest["job_id"],
                      agent=worker_id, payout_muc=result["payout_muc"],
                      fee_muc=result["fee_muc"],
                      emitted_dyn_mu=result["emitted_dyn_mu"])
        return result

    def refund(self, *, ledger: WorkLedger, day: int) -> dict:
        self._require(statuses=("checked_fail", "denied"))
        if self.manifest["status"] == "denied":
            note = "refunded: the buyer denied the study — escrow back, fees 0, emission 0"
        else:
            last = self.manifest["checks"][-1]
            if last["passed"]:
                raise CraftError("refund requires a FAIL round — the evidence on disk does not show one")
            note = "refunded: the build never passed — escrow back, fees 0, emission 0"
        self.manifest["status"] = "refunded"
        self.manifest["note"] = note
        self._save()
        ledger.append(day=day, kind="refund", job_id=self.manifest["job_id"],
                      agent=self.manifest["worker"] or "unassigned",
                      escrow_back_muc=self.manifest["escrow_usds_muc"],
                      emitted_dyn_mu=0)
        return {"escrow_back_muc": self.manifest["escrow_usds_muc"],
                "fee_muc": 0, "emitted_dyn_mu": 0}

    # ---------- the published proof ----------
    def post(self, *, day: int) -> dict:
        self._require(statuses=("settled",))
        last = self.manifest["checks"][-1]
        body = [f"title: Crafted {self.manifest['job_id']} — {self.manifest['request']}",
                "lang: en", "tags: craft, rebuild, evidence", "",
                f"Target: {self.manifest['target']['kind']} `{self.manifest['target']['ref']}`.",
                f"Final round {last['round']}: {last['similarity_milli'] / 10:.0f}% alike; "
                + ", ".join(c["title"] for c in last["claims"] if c["passed"]) + ".",
                "", "The build below is the shipped bytes.", ""]
        for name in sorted((self.root / "app").glob("*")):
            body.append(f"```{name.suffix.lstrip('.') or 'text'}")
            body.append(name.read_text(encoding="utf-8").rstrip())
            body.append("```")
        wire = to_wire(parse_post("\n".join(body) + "\n"),
                       post_id=f"post-craft-{self.manifest['job_id']}",
                       author=self.manifest["worker"] or "unassigned", day=day)
        pdir = self.root / "post"
        pdir.mkdir(exist_ok=True)
        (pdir / "post.wire.json").write_text(
            json.dumps(wire, indent=1, sort_keys=True) + "\n")
        self.manifest["post"] = {"wire": "post/post.wire.json",
                                 "embeds": len(wire["embeds"])}
        self._save()
        return wire

    # ---------- inbox: open questions and the buyer's approval cards ----------
    def _ask(self, qid: str, question: str, kind: str = "question") -> None:
        inbox = self.root / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / f"{qid}.json").write_text(json.dumps(
            {"id": qid, "kind": kind, "question": question,
             "status": "open", "answer": "", "answered_by": ""},
            indent=1, sort_keys=True) + "\n")

    def _open_approval(self) -> str | None:
        inbox = self.root / "inbox"
        if not inbox.is_dir():
            return None
        for p in sorted(inbox.glob("*.json")):
            item = json.loads(p.read_text())
            if item.get("kind") == "approval" and item.get("status") == "open":
                return item["id"]
        return None

    def _no_open_approval(self, what: str) -> None:
        open_card = self._open_approval()
        if open_card:
            raise CraftError(f"{open_card} is open — the buyer approves or denies before {what}")

    def ask_approval(self, question: str) -> str:
        """A scope change mid-loop: the buyer decides before the loop goes on."""
        qid = f"q-{len(list((self.root / 'inbox').glob('*.json'))) + 1:03d}" \
            if (self.root / "inbox").is_dir() else "q-001"
        self._ask(qid, question, kind="approval")
        return qid

    def answer(self, qid: str, answer: str, *, by: str | None = None,
               ledger: WorkLedger | None = None, day: int = 1) -> dict:
        p = self.root / "inbox" / f"{qid}.json"
        if not p.is_file():
            raise CraftError(f"no such question: {qid}")
        item = json.loads(p.read_text())
        if item["status"] != "open":
            raise CraftError(f"{qid} is already answered — a decision is on the record once")
        if item.get("kind") == "approval":
            if not by:
                raise CraftError("an approval card names its answerer — pass by=<buyer>")
            if by != self.manifest["buyer"]:
                raise CraftError(f"only the buyer ({self.manifest['buyer']}) may answer "
                                 f"an approval card, not {by}")
            answer = answer.strip().lower()
            if answer not in ("approve", "deny"):
                raise CraftError("an approval card is answered approve or deny")
            if answer == "deny":
                self.manifest["status"] = "denied"
                self.manifest["note"] = f"denied by the buyer ({qid}) — the loop ends, escrow returns via refund"
                self._save()
        item["status"] = "answered"
        item["answer"] = answer
        item["answered_by"] = by or "unknown"
        p.write_text(json.dumps(item, indent=1, sort_keys=True) + "\n")
        if item.get("kind") == "approval" and ledger is not None:
            ledger.append(day=day, kind="approve", job_id=self.manifest["job_id"],
                          agent=by or "unknown", decision=answer, card=qid)
        return item

    # ---------- plumbing ----------
    def _require(self, statuses: tuple[str, ...]) -> None:
        if not self.manifest:
            raise CraftError(f"{self.root} is not a craft job — run open first")
        if self.manifest["status"] not in statuses:
            raise CraftError(f"status is {self.manifest['status']!r}; this step needs one of "
                             f"{', '.join(statuses)} — the loop refuses to skip steps")

    def _save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest["updated_ms"] = int(time.time() * 1000)
        self.manifest_path.write_text(
            json.dumps(self.manifest, indent=1, sort_keys=True) + "\n")


# --------------------------------------------------------------------------
# CLI — each subcommand is one agent tool call, as craft-anything does it
# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dyn_craft",
                                 description="dyn.craft.v1 — the craft loop, where it pays")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("open")
    p.add_argument("root"); p.add_argument("--job-id", required=True)
    p.add_argument("--buyer", required=True); p.add_argument("--request", required=True)
    p.add_argument("--kind", required=True, choices=["web", "file"])
    p.add_argument("--ref", required=True)
    p.add_argument("--value-usds", type=int, default=500)
    p.add_argument("--max-rounds", type=int, default=DEFAULT_MAX_ROUNDS)
    p.add_argument("--good-enough", type=float, default=DEFAULT_GOOD_ENOUGH)
    p.add_argument("--day", type=int, default=1)
    p = sub.add_parser("study"); p.add_argument("root"); p.add_argument("--day", type=int, default=1)
    p = sub.add_parser("build"); p.add_argument("root"); p.add_argument("--worker", required=True)
    p.add_argument("--files", required=True, help="JSON object: name -> content")
    p.add_argument("--day", type=int, default=1)
    p = sub.add_parser("check"); p.add_argument("root"); p.add_argument("--day", type=int, default=1)
    p = sub.add_parser("settle"); p.add_argument("root"); p.add_argument("--day", type=int, default=1)
    p = sub.add_parser("refund"); p.add_argument("root"); p.add_argument("--day", type=int, default=1)
    p = sub.add_parser("post"); p.add_argument("root"); p.add_argument("--day", type=int, default=1)
    p = sub.add_parser("answer"); p.add_argument("root"); p.add_argument("--qid", required=True)
    p.add_argument("--answer", required=True)
    p.add_argument("--by", help="who answers (the buyer, for approval cards)")
    p.add_argument("--day", type=int, default=1)
    sub.add_parser("demo")
    a = ap.parse_args(argv)

    if a.cmd == "demo":
        return demo()

    ledger = WorkLedger()
    job = CraftJob(a.root)
    if a.cmd == "open":
        m = job.open(job_id=a.job_id, buyer=a.buyer, request=a.request,
                     target_kind=a.kind, target_ref=a.ref,
                     value_usds=a.value_usds, max_rounds=a.max_rounds,
                     good_enough=a.good_enough, ledger=ledger, day=a.day)
        print(f"opened {m['job_id']} — escrow {m['escrow_usds_muc'] // 1_000_000} USDS, "
              f"rounds ≤ {m['rounds']['max']}, good-enough {m['good_enough']:.0f}%")
    elif a.cmd == "study":
        r = job.study(ledger=ledger, day=a.day)
        print(f"study: {len(r['evidence'])} evidence record(s), {len(r['unknowns'])} open question(s)")
    elif a.cmd == "build":
        r = job.build(worker=a.worker, files=json.loads(a.files), ledger=ledger, day=a.day)
        print("build recorded: " + ", ".join(sorted(r)))
    elif a.cmd == "check":
        r = job.check(ledger=ledger, day=a.day)
        print(f"round {r['round']}: {r['check']} — "
              f"{'PASS' if r['passed'] else 'FAIL'}, similarity "
              f"{r['similarity_milli'] / 10:.0f}%, "
              f"claims {sum(c['passed'] for c in r['claims'])}/{len(r['claims'])}")
    elif a.cmd == "settle":
        r = job.settle(ledger=ledger, day=a.day)
        print(f"settled: payout {r['payout_muc']:,} µ¢ (fee {r['fee_muc']:,}), "
              f"emitted {r['emitted_dyn_mu']:,} DYN µ, chain_ok={r['chain_ok']}")
    elif a.cmd == "refund":
        r = job.refund(ledger=ledger, day=a.day)
        print(f"refunded: escrow {r['escrow_back_muc']:,} µ¢ back, fees 0, emission 0")
    elif a.cmd == "post":
        wire = job.post(day=a.day)
        print(f"posted {wire['post_id']} — {len(wire['embeds'])} verifiable embed(s)")
    elif a.cmd == "answer":
        item = job.answer(a.qid, a.answer, by=a.by,
                          ledger=WorkLedger(), day=a.day)
        print(f"{item['id']} answered ({item['kind']}) by {item['answered_by']}: {item['answer']}")
    return 0


def demo() -> int:
    """The whole craft loop on a real target: study → build → check → settle → post."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "dataset.json"
        target.write_text(json.dumps(
            {"invoices": [{"id": f"inv-{i:05d}", "cents": 1_000 + i}
                          for i in range(120)], "currency": "USD"}, indent=1) + "\n")
        root = Path(td) / "craft-0001"
        for args in (["open", str(root), "--job-id", "craft-0001",
                      "--buyer", "agent-buyer",
                      "--request", "A program that reports this dataset's facts",
                      "--kind", "file", "--ref", str(target)],
                     ["study", str(root)]):
            main(args)
        # the buyer approves the study — the card the loop pauses on
        card = next(json.loads(p.read_text()) for p in sorted((root / "inbox").glob("*.json"))
                    if json.loads(p.read_text())["kind"] == "approval"
                    and json.loads(p.read_text())["status"] == "open")
        main(["answer", str(root), "--qid", card["id"], "--answer", "approve",
              "--by", "agent-buyer"])
        facts = json.loads((root / "capture" / "facts.json").read_text())
        main(["build", str(root), "--worker", "agent-worker", "--files", json.dumps({
            "main.py": f'''#!/usr/bin/env python3
"""Reports the facts of the studied dataset, exactly as study measured them."""
import hashlib, json, sys

raw = open(sys.argv[1], "rb").read()
kind = "json" if raw[:1] in (b"{{", b"[") else "text"
lines = raw.count(b"\\n")
print(json.dumps({{"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                   "lines": {facts['lines']}, "type": kind}}))
'''})])
        main(["check", str(root)])
        main(["settle", str(root)])
        main(["post", str(root)])
        m = json.loads((root / "craft.json").read_text())
        print(f"\nfinal: {m['status']} — round {m['rounds']['done']}, "
              f"{m['checks'][-1]['similarity_milli'] / 10:.0f}% alike; "
              f"a folder any witness can re-check.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
