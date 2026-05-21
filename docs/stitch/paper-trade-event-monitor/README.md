# Paper Trade Event Monitor Stitch References

Status: Metadata captured; screenshots and HTML assets not downloaded yet.

This folder supports M16.1 of `docs/TAURUS_REACT_DASHBOARD_PLAN.md`.

## What Is Here

- `STITCH_MANIFEST.md`: saved Stitch project metadata, design-system IDs, requested screen IDs, hosted screenshot URLs, hosted HTML URLs, and suggested local filenames.

## What M16.1 Still Needs To Do

- Create `docs/stitch/paper-trade-event-monitor/assets/`.
- Use the URLs in `STITCH_MANIFEST.md` with `curl -L`.
- Save each screenshot and generated HTML file with the suggested filenames.
- Update this README with a list of downloaded files and any failures.
- Keep the assets as reference material only.

## Source Project

- Title: Paper Trade Event Monitor
- Project ID: `16481042039965443151`
- Resource: `projects/16481042039965443151`
- Design system asset: `assets/5358cfbb776e4117a8e412e6740f0d0f`
- Design system name: Deep Space Observability

## Requested Screens

| Screen | ID | Suggested screenshot |
|---|---|---|
| Taurus Run Overview (Dark) - v2 | `2777072278569602314` | `01-run-overview-dark-v2.png` |
| Run Detail: pr-20231027-01 (Dark) - v2 | `6155813548408423466` | `02-run-detail-dark-v2.png` |
| INFY Decision Trail (Dark) - v3 | `1010b4cbc2bb4316a2048a428dcca3a7` | `03-infy-decision-trail-dark-v3.png` |
| Taurus Risk Engine (Dark) | `8acc13409def47ab8bcbaa89db68cbc3` | `04-risk-engine-dark.png` |
| Taurus Portfolio & Account (Dark) | `99a3894cc36d437cb6f93e1c92f2fc10` | `05-portfolio-account-dark.png` |
| Taurus Decision Replay (Dark) | `3eaa09ed3da44b31aa7765e3504763aa` | `06-decision-replay-dark.png` |
| Taurus Run History (Dark) | `7697aed1e06248d9a26ff44fbee2e5fd` | `07-run-history-dark.png` |

## Usage Rule

Do not directly port the generated Stitch HTML into production React code. Use it as reference for layout, spacing, information hierarchy, and visual direction. Build maintainable React components in `apps/web`.
