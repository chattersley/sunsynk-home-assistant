# Issue analysis — GitHub issues #1–#4

One doc per open issue. Each walks the reported problem, verifies against
the reporter's live Home Assistant instance, challenges the suggested
direction where relevant, and sketches an implementation plan for review
before coding starts.

| # | Issue | Verdict |
|---|---|---|
| [1](issue-01-power-unit-scaling.md) | Inverter power values appear 1,000× too large | Real defect — four cascading causes, land as one release |
| [2](issue-02-grid-trickle-feed.md) | Add Grid Trickle Feed (`zeroExportPower`) | Sensible addition, small scope |
| [3](issue-03-total-solar-capacity.md) | Add Total Solar Capacity sensor | Sensible addition, field already fetched |
| [4](issue-04-status-codes-to-text.md) | Render numeric status codes as text | Good idea; partial-coverage trade-off to discuss |

Suggested landing order: **#1 first** (bug, user pain), then **#3** (single
sensor, risk-free), then **#2** (one new write entity), then **#4** (coupled
with label-table research). #1 and #4 both involve breaking the declared
contract of existing sensors and want prominent release-note callouts.
