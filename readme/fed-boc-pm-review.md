# Fed/BOC Portfolio Manager Review Gate

The Fed/BOC watcher is not publishable immediately after collection. A separate
review agent must assess the frozen candidate as a portfolio manager whose own
portfolio and P&L depend on the page being correct.

## Role separation

- **Operator agent:** collects and assembles the candidate payload. It may not
  approve its own work.
- **PM reviewer agent:** receives a frozen candidate and evidence, challenges
  every material claim, and writes only the structured review artifact.
- **Publisher:** may archive, commit, sync, or push only after the review gate
  validates an `approved` verdict bound to the exact candidate bytes.

The PM reviewer is independent and time-constrained. It must be skeptical,
direct, and specific. It does not reward effort. It asks whether it would risk
real capital based on this snapshot.

## Frozen artifacts

For Toronto date `YYYY-MM-DD` and iteration `NN`:

```text
review/fed-boc/YYYY-MM-DD/iteration-NN/
  candidate.json
  candidate.sha256
  pm-review.json
```

`candidate.json` is an exact copy of the proposed
`docs/data/fed-boc-dashboard.json`. Once sent for review it is immutable.
`candidate.sha256` contains its SHA-256 digest. `pm-review.json` must cite that
same digest. These review folders are durable audit evidence and are committed
with an approved publication.

## PM review mandate

The reviewer must independently check, not merely summarize:

1. Fed and BoC meeting dates, last decisions, target rates, vote/dissent text,
   and next-decision labels against official sources.
2. Every probability sums to approximately 1, is internally consistent with
   rates/futures, and is labelled as direct pricing versus a proxy. A
   multi-meeting quarterly contract must not be presented as a clean
   single-meeting probability.
3. Every driver belongs on the correct dovish/hawkish side, has a current,
   traceable source, separates Actual/Forecast/Previous, and has a weight
   proportional to evidence and market relevance.
4. Dates, timezone offsets, release chronology, units, signs, basis points,
   percentages, and cross-field statements agree.
5. Market-validation moves match the claimed transmission mechanism. Correlation
   is not presented as causation.
6. Stale, duplicated, superseded, contradictory, or low-signal items are removed
   or clearly qualified.
7. The top-level `as_of`, nested observation times, version, snapshot date, and
   freshness claim are mutually consistent.
8. The output is decision-useful: what changed, why it matters, what is priced,
   what could falsify the view, and the largest P&L risks are clear without
   wasting the PM's time.

The reviewer must use tools to inspect official/current sources where needed.
It must never approve based solely on the operator's verification note.

## Verdict contract

The reviewer writes `pm-review.json` matching
`review/fed-boc/pm-review.schema.json`.

- `approved`: no unresolved `critical` or `major` finding; the candidate is safe
  to publish as a decision-support snapshot. Findings may contain only minor
  presentation observations.
- `revise`: one or more material problems exist. Every finding must identify the
  field, evidence, why it affects a trading decision/P&L, and an executable
  instruction to the operator.

Approval must not be conditional. “Approved if fixed” is `revise`.

## Revision loop

1. Operator freezes iteration 01 and launches a separate PM reviewer.
2. Run `econ/validate_pm_review.py --candidate ... --review ...`.
3. If verdict is `revise`, publication is forbidden. Immediately run
   `econ/record_pm_feedback.py --candidate ... --review ...`; this atomically
   updates `review/fed-boc/feedback/latest.json` and appends an immutable
   history record. The operator then follows every instruction, re-triggers
   collection for every affected source/claim, rebuilds the whole internally
   consistent candidate, and freezes iteration 02.
4. A fresh PM reviewer reviews iteration 02 from scratch. The operator may not
   edit or reinterpret the prior verdict into approval.
5. At the beginning of every later cron run, read
   `review/fed-boc/feedback/latest.json` before any collection. If its status is
   `open`, every required recollection and operator instruction is mandatory;
   a normal incremental refresh is not sufficient. Include the feedback and a
   remediation/evidence mapping in the next PM handoff so the reviewer can
   detect repeat failures.
6. Repeat until approval, with a maximum of 3 iterations per scheduled run.
   Exhaustion fails closed and leaves the prior public/latest output untouched;
   the open feedback remains mandatory on the next run.
7. On approval, run the validator with `--require-approved`, then archive,
   test, commit, sync, push, and verify the live artifact.

A failed or missing reviewer, malformed artifact, digest mismatch, or stale
approval always blocks publication.