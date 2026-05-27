# Paper Trade Event Monitor Stitch References

Status: Preserved future UI reference assets.

Fetched: 2026-05-21 17:00 IST

This folder preserves Stitch-generated visual references for future Taurus UI work.

## Source Project

- Title: Paper Trade Event Monitor
- Project ID: `16481042039965443151`
- Resource: `projects/16481042039965443151`
- Design system asset: `assets/5358cfbb776e4117a8e412e6740f0d0f`
- Design system name: Deep Space Observability
- Design system mode: Dark

## What Is Here

- `STITCH_MANIFEST.md`: saved Stitch project metadata, design-system IDs, requested screen IDs, hosted screenshot URLs, hosted HTML URLs, and suggested local filenames.
- `assets/`: local reference screenshots and generated HTML files fetched from the Stitch URLs.

## Downloaded Screens

| Route | Stitch screen | Screen ID | Screenshot | HTML |
|---|---|---|---|---|
| `/` | Taurus Run Overview (Dark) - v2 | `2777072278569602314` | `assets/01-run-overview-dark-v2.png` | `assets/01-run-overview-dark-v2.html` |
| `/runs/:runId` | Run Detail: pr-20231027-01 (Dark) - v2 | `6155813548408423466` | `assets/02-run-detail-dark-v2.png` | `assets/02-run-detail-dark-v2.html` |
| `/runs/:runId/symbols/:symbol` | INFY Decision Trail (Dark) - v3 | `1010b4cbc2bb4316a2048a428dcca3a7` | `assets/03-infy-decision-trail-dark-v3.png` | `assets/03-infy-decision-trail-dark-v3.html` |
| `/risk` | Taurus Risk Engine (Dark) | `8acc13409def47ab8bcbaa89db68cbc3` | `assets/04-risk-engine-dark.png` | `assets/04-risk-engine-dark.html` |
| `/portfolio` | Taurus Portfolio & Account (Dark) | `99a3894cc36d437cb6f93e1c92f2fc10` | `assets/05-portfolio-account-dark.png` | `assets/05-portfolio-account-dark.html` |
| `/replay/:decisionId` | Taurus Decision Replay (Dark) | `3eaa09ed3da44b31aa7765e3504763aa` | `assets/06-decision-replay-dark.png` | `assets/06-decision-replay-dark.html` |
| `/history` | Taurus Run History (Dark) | `7697aed1e06248d9a26ff44fbee2e5fd` | `assets/07-run-history-dark.png` | `assets/07-run-history-dark.html` |

## Visual Tokens

Derived from Deep Space Observability and the historical Taurus React dashboard planning work:

| Token | Value |
|---|---|
| Background | `#0b1326` |
| Surface lowest | `#060e20` |
| Surface low | `#131b2e` |
| Surface | `#171f33` |
| Surface high | `#222a3d` |
| Surface highest | `#2d3449` |
| Outline | `#3e484f` |
| Primary accent | `#8ed5ff` |
| Primary container | `#38bdf8` |
| Secondary accent | `#c0c1ff` |
| Secondary container | `#3131c0` |
| Text | `#dae2fd` |
| Muted text | `#bdc8d1` |
| Error/failure | `#ffb4ab` |
| Success | Green semantic token for approved, complete, and filled states |
| Caution | Amber semantic token for partial, stale, reduced, or warning states |
| Typography | Inter for UI; monospace for IDs and raw JSON |
| Base spacing | `4px`; page gutter `1.5rem` |

Future UI work should convert these into Tailwind/CSS tokens rather than copying static Stitch styles.

## Route Mapping

| Stitch reference | Taurus React route |
|---|---|
| Run Overview | `/` |
| Run Detail | `/runs/:runId` |
| Decision Trail | `/runs/:runId/symbols/:symbol` |
| Decision Replay | `/replay/:decisionId` |
| Risk Engine | `/risk` |
| Portfolio & Account | `/portfolio` |
| Run History | `/history` |

## Scope Rule

These assets are references only. Do not directly port the generated Stitch HTML into production React code. Use the screenshots and HTML to understand layout, spacing, information hierarchy, and visual direction, then build clean components in `apps/web`.

The current React dashboard remains read-only. Any Stitch mock action that implies mutation or run control, such as a "Run Agent" control, is non-functional reference material and must not be implemented as a Taurus API action without a new explicit milestone.
