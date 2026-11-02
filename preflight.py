"""Preflight: the whole Safe to Send series in one command.

Takes a campaign package (the agent's tool calls, the delivery, and the model-written
summary for the market) and runs five gates in order:
  1. policy     - every agent call decided, fail closed            (Ep 02-03)
  2. QA         - pre-send checks on the delivery                  (Ep 05)
  3. lock       - the summary may not contradict the verdict       (Ep 12)
  4. approvals  - who must sign before it can go                   (Ep 13)
  5. audit      - every result chained into a tamper-evident log   (Ep 06)
Prints GO / NO-GO with the reasons and the audit head hash. Standard library only.
"""
import hashlib
import json
import re
import sys

# 1. policy
def decide(call):
    t = call["tool"]
    if t in ("schema_browse", "audience_count"):
        return "allow"
    if t == "query_run":
        if re.search(r"\b(insert|update|delete|drop|truncate|alter)\b", call.get("sql", ""), re.I):
            return "block"
        return "allow_masked" if call.get("pii") else "allow"
    if t == "js_execute":
        return "dry_run"
    return "block"

# 2. QA
def qa(d):
    issues = []
    if not re.search(r'href="[^"]*unsubscribe', d["html"], re.I):
        issues.append("no unsubscribe link")
    if re.search(r"€\s?\d{1,3}(,\d{3})*\.\d{2}", d["html"]):
        issues.append("English price format")
    if "marketing_optin" not in d.get("filters", []):
        issues.append("no consent filter")
    if not "08:00" <= d["send_time"] <= "21:00":
        issues.append(f"send at {d['send_time']} outside 08:00-21:00")
    if not d.get("proof_by"):
        issues.append("no proof sign-off")
    return issues

# 3. lock
GREEN = r"ready to send|looks good|all clear|good to go|\bpassed\b"

def lock(qa_issues, summary):
    if qa_issues and re.search(GREEN, summary, re.I):
        return ["summary gives a green light on a failed delivery"]
    return []

# 4. approvals
def approvers_needed(volume):
    return 2 if volume > 100_000 else 1

# 5. audit
def chain(entries):
    prev, out = "0" * 64, []
    for e in entries:
        h = hashlib.sha256((json.dumps(e, sort_keys=True) + prev).encode()).hexdigest()
        out.append({**e, "prev": prev, "hash": h})
        prev = h
    return out, prev


def preflight(pkg):
    reasons, log = [], []
    decisions = [(c["tool"], decide(c)) for c in pkg["agent_calls"]]
    blocked = [t for t, d in decisions if d == "block"]
    log.append({"gate": "policy", "decisions": decisions})
    if blocked:
        reasons.append(f"agent attempted {len(blocked)} blocked action(s): {', '.join(blocked)}")
    issues = qa(pkg["delivery"])
    log.append({"gate": "qa", "issues": issues})
    reasons += [f"QA: {i}" for i in issues]
    lock_issues = lock(issues, pkg["summary"])
    log.append({"gate": "lock", "issues": lock_issues})
    reasons += [f"summary: {i}" for i in lock_issues]
    need = approvers_needed(pkg["delivery"]["volume"])
    log.append({"gate": "approvals", "needed": need})
    verdict = "NO-GO" if reasons else "GO"
    log.append({"gate": "verdict", "verdict": verdict})
    chained, head = chain(log)
    return {"verdict": verdict, "reasons": reasons, "approvers": need, "audit": chained, "head": head}


def main(paths):
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            pkg = json.load(fh)
        r = preflight(pkg)
        d = pkg["delivery"]
        print(f"{d['id']} ({d['market']}, {d['volume']:,} recipients): {r['verdict']}")
        for reason in r["reasons"]:
            print(f"   - {reason}")
        if r["verdict"] == "GO":
            print(f"   next: {r['approvers']} named approver(s), then send")
        print(f"   audit head: {r['head'][:16]}…\n")


if __name__ == "__main__":
    main(sys.argv[1:] or ["examples/hr_package.json", "examples/gr_package.json"])
