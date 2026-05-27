# Stitch Asset Manifest - Paper Trade Event Monitor

Captured: 2026-05-21 16:42 IST

Project:

- Title: Paper Trade Event Monitor
- ID: `16481042039965443151`
- Resource: `projects/16481042039965443151`
- Visibility: Private

Purpose:

- This manifest preserves the Stitch metadata needed to download the reference assets for M16.1.
- The downloaded screenshots and HTML are references only. Do not port the generated HTML directly into production React components.

## Design System

Requested design-system screen:

- User-provided ID: `asset-stub-assets-5358cfbb776e4117a8e412e6740f0d0f-1779350842288`
- Stitch project instance ID: `assets-5358cfbb776e4117a8e412e6740f0d0f-1779350842288`
- Source asset: `assets/5358cfbb776e4117a8e412e6740f0d0f`
- Display name: `Deep Space Observability`
- Version: `1`
- Color mode: `DARK`

Important tokens:

| Token | Value |
|---|---|
| `background` | `#0b1326` |
| `surface-container-lowest` | `#060e20` |
| `surface-container-low` | `#131b2e` |
| `surface-container` | `#171f33` |
| `surface-container-high` | `#222a3d` |
| `surface-container-highest` | `#2d3449` |
| `outline-variant` | `#3e484f` |
| `on-surface` | `#dae2fd` |
| `on-surface-variant` | `#bdc8d1` |
| `primary` | `#8ed5ff` |
| `primary-container` | `#38bdf8` |
| `secondary` | `#c0c1ff` |
| `secondary-container` | `#3131c0` |
| `error` | `#ffb4ab` |
| `font` | `Inter` |
| `base spacing` | `4px` |
| `gutter` | `1.5rem` |

Notes:

- Design-system metadata is fetched through Stitch project/design-system APIs, not by `curl`.
- If a future implementation needs a local token file, derive it from this manifest and the Stitch `list_design_systems` response.

## Requested Screens

Use the `screenshot_url` and `html_url` values below with `curl -L`.

Example:

```bash
mkdir -p docs/stitch/paper-trade-event-monitor/assets
curl -L '<screenshot_url>' -o docs/stitch/paper-trade-event-monitor/assets/01-run-overview-dark-v2.png
curl -L '<html_url>' -o docs/stitch/paper-trade-event-monitor/assets/01-run-overview-dark-v2.html
```

### 1. Taurus Run Overview (Dark) - v2

- Screen ID: `2777072278569602314`
- Resource: `projects/16481042039965443151/screens/2777072278569602314`
- Device: `DESKTOP`
- Size: `2560x2048`
- Suggested screenshot filename: `01-run-overview-dark-v2.png`
- Suggested HTML filename: `01-run-overview-dark-v2.html`
- Screenshot file resource: `projects/16481042039965443151/files/2777072278569599597`
- HTML file resource: `projects/16481042039965443151/files/2777072278569600976`
- Screenshot URL: `https://lh3.googleusercontent.com/aida/ADBb0ui-bv67TSOVK3oqMJF7YFyG-iPoI1R0KPFXd_b7XDbft5tGyfbpY7I0tBj4fbx-F1zQ_z509KFcbmKV4o2oYgDbyvTrjYB_3Yf3kL5pstdLfhOypEipFkSBbtei4oZtSoQBzckKISn0YajuyS0mKWsdI0GoNbRivBkz6LABhrYOysOkjhHKWECBz_fAZOGS32E8NutBnXiZyOr8g9EzqkGLtCDdP0NLf4t4Rs5PtDM-YrKWYiEVhttX70Y`
- HTML URL: `https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ8Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpbCiVodG1sXzAwMDY1MjUwZGZkNjhkNDEwODE2ZWFhMjIxMjdkNWZmEgsSBxCd6OLZ-h4YAZIBJAoKcHJvamVjdF9pZBIWQhQxNjQ4MTA0MjAzOTk2NTQ0MzE1MQ&filename=&opi=89354086`

### 2. Run Detail: pr-20231027-01 (Dark) - v2

- Screen ID: `6155813548408423466`
- Resource: `projects/16481042039965443151/screens/6155813548408423466`
- Device: `DESKTOP`
- Size: `2560x2048`
- Suggested screenshot filename: `02-run-detail-dark-v2.png`
- Suggested HTML filename: `02-run-detail-dark-v2.html`
- Screenshot file resource: `projects/16481042039965443151/files/6155813548408425565`
- HTML file resource: `projects/16481042039965443151/files/6155813548408423568`
- Screenshot URL: `https://lh3.googleusercontent.com/aida/ADBb0uj5LJ3pbERNoSyRFUlVBVfM0dnQvHESWpztQR-bH4ZjGV5Ir51XW6F_3S6ZTpP_HI3kuo5p1gMJByBRd9qLLAawXRB-0-x6FV_A8c4h8WQQPxiTB3iCtN3t5e0buzFES9A-ioSLCfuY2B5YkpfO6yxiOERINv6Rg_5NANERcOYDqMDpzKTkfloel7CcChs3WzSWztUew_jLegzAPE4NV_QB742u3PziSCn8f1FIqiwzkL9rHpyOlbfw2ZyW`
- HTML URL: `https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ8Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpbCiVodG1sXzAwMDY1MjUwZGZiYTdmZTQwN2M0ZDBkM2RmMDIwYmNlEgsSBxCd6OLZ-h4YAZIBJAoKcHJvamVjdF9pZBIWQhQxNjQ4MTA0MjAzOTk2NTQ0MzE1MQ&filename=&opi=89354086`

### 3. INFY Decision Trail (Dark) - v3

- Screen ID: `1010b4cbc2bb4316a2048a428dcca3a7`
- Resource: `projects/16481042039965443151/screens/1010b4cbc2bb4316a2048a428dcca3a7`
- Device: `DESKTOP`
- Size: `2560x2498`
- Suggested screenshot filename: `03-infy-decision-trail-dark-v3.png`
- Suggested HTML filename: `03-infy-decision-trail-dark-v3.html`
- Screenshot file resource: `projects/16481042039965443151/files/3af31499bdf34e7ea875290fa96c32bb`
- HTML file resource: `projects/16481042039965443151/files/793240de71be4e5ca39a260afd858e03`
- Screenshot URL: `https://lh3.googleusercontent.com/aida/ADBb0ujPLejWzv7uTiYrzCRAKKvmXnMLF01n19ZVNycK7lwaaOekJRBWnZeCiYsfinrNDcvAClSd5b5vWmF0qs_oIqEnDXR3LZyg2NwE1MoC-Tj738ic5FhkkIUuyQNdaKlcLKFNwBIuk6ZNp6UKhRZ8gQ218FyEz79chWPB-uIt_GD1yiGjC08fdq0S-HksmbQqG2rZYDdH-KEedNT9OxHMNdHAVT7-C83CmMDT1DMavN4ZmolNyAfmty1WlFQ`
- HTML URL: `https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ8Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpbCiVodG1sX2FlNTBiYmU2YzZlNDRiZmY4Y2IxYTVkMTZmM2U2YmU5EgsSBxCd6OLZ-h4YAZIBJAoKcHJvamVjdF9pZBIWQhQxNjQ4MTA0MjAzOTk2NTQ0MzE1MQ&filename=&opi=89354086`

### 4. Taurus Risk Engine (Dark)

- Screen ID: `8acc13409def47ab8bcbaa89db68cbc3`
- Resource: `projects/16481042039965443151/screens/8acc13409def47ab8bcbaa89db68cbc3`
- Device: `DESKTOP`
- Size: `2560x2048`
- Suggested screenshot filename: `04-risk-engine-dark.png`
- Suggested HTML filename: `04-risk-engine-dark.html`
- Screenshot file resource: `projects/16481042039965443151/files/d4f8f9e537224623b2b7c084f3746e87`
- HTML file resource: `projects/16481042039965443151/files/09dc269babc2413fb2a5ac972f387018`
- Screenshot URL: `https://lh3.googleusercontent.com/aida/ADBb0ui3Yd3difL_U81O8NJrp4EVaDRqjnV1w_ZAOi_YjqFcFFTwh7GWlJNmkzr351H1gjK3ibD1bFvIJUcXLDnS7jAlOD-aXAaaMJFafBV6-v7wIPEISAfxgi_WzsutktZKgehWCWgKK62wqtZ5nPmqyPvcprBt2dBoDXV1npXdFe49pcw7vCod98_QuijYWmvbpHpp-KF5OFQecddcuUwNYq2zgbRFPQH1n-ZxxrRsa4Imy-0hVWOVfkGhG-Yh`
- HTML URL: `https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ8Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpbCiVodG1sXzMwZDZhNDRhYmQ5OTQ3MDQ4ZGE0ODY4Mjk4NjE2NWI2EgsSBxCd6OLZ-h4YAZIBJAoKcHJvamVjdF9pZBIWQhQxNjQ4MTA0MjAzOTk2NTQ0MzE1MQ&filename=&opi=89354086`

### 5. Taurus Portfolio & Account (Dark)

- Screen ID: `99a3894cc36d437cb6f93e1c92f2fc10`
- Resource: `projects/16481042039965443151/screens/99a3894cc36d437cb6f93e1c92f2fc10`
- Device: `DESKTOP`
- Size: `2560x2048`
- Suggested screenshot filename: `05-portfolio-account-dark.png`
- Suggested HTML filename: `05-portfolio-account-dark.html`
- Screenshot file resource: `projects/16481042039965443151/files/bcc677f7991d4d6180363e5499f7625d`
- HTML file resource: `projects/16481042039965443151/files/4f85ebbb221f40e7996170aaf8391dda`
- Screenshot URL: `https://lh3.googleusercontent.com/aida/ADBb0ug1sf9wXK-u-dOEOtgMolV1QFev8cigA2MFpl6NuoVuH1vic5dZ14ymXL4FvpHJcTlPitnkLge_K_ps6bJLicsxUnEnN4hWrgS81TQ1j1v5A9O3NEqlnKzj7tP-_9fovAqCdULl1I9ay7BUmsTAMx_QwYZReD-0u0xLGaMiOALN8wmYCjJVfBjSVbV76iJUYpU6xboEFZlrKNFuZdNVBtGjqNf4m-WNJQIvNbCDMdWnm4_oeo5gVh1IsTKz`
- HTML URL: `https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ8Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpbCiVodG1sX2U1ODliY2UyYjNiOTQxMDA5ZGE2MDk0NGM1Y2VlYjJmEgsSBxCd6OLZ-h4YAZIBJAoKcHJvamVjdF9pZBIWQhQxNjQ4MTA0MjAzOTk2NTQ0MzE1MQ&filename=&opi=89354086`

### 6. Taurus Decision Replay (Dark)

- Screen ID: `3eaa09ed3da44b31aa7765e3504763aa`
- Resource: `projects/16481042039965443151/screens/3eaa09ed3da44b31aa7765e3504763aa`
- Device: `DESKTOP`
- Size: `2560x2176`
- Suggested screenshot filename: `06-decision-replay-dark.png`
- Suggested HTML filename: `06-decision-replay-dark.html`
- Screenshot file resource: `projects/16481042039965443151/files/5eca40ce4df8469a950a9309d7c40336`
- HTML file resource: `projects/16481042039965443151/files/6643866b833c4383a4647fa326ba14ea`
- Screenshot URL: `https://lh3.googleusercontent.com/aida/ADBb0uiPx-b5abrkyTi1qGGn8GrpL6DXwKcrfu88qVV4SO6GiVpfJkq6yij7OJELeZ5hxVZL3Z9OsZTR2tsPNR4TWaNlhHh_DSc6rDWOrQl8s8Pzmb7KtHUSyXM1iOqTPAhg6yyAoXbz9jcxGWEp6_NYcq0RbpNkYcvwjxYqFaguL9NTe2f0qNN4Qnse1z-fPhj9dkkpSIYRUN2s6ty9kAsR7ibLajc4jBYsTIr0eNAFWfa4R4DwsUC3iP_ggLID`
- HTML URL: `https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ8Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpbCiVodG1sX2E2NDU0MjU4YTNjNTQ3ODBiMGYzMGFiZGQ0NTE2NWI4EgsSBxCd6OLZ-h4YAZIBJAoKcHJvamVjdF9pZBIWQhQxNjQ4MTA0MjAzOTk2NTQ0MzE1MQ&filename=&opi=89354086`

### 7. Taurus Run History (Dark)

- Screen ID: `7697aed1e06248d9a26ff44fbee2e5fd`
- Resource: `projects/16481042039965443151/screens/7697aed1e06248d9a26ff44fbee2e5fd`
- Device: `DESKTOP`
- Size: `2560x2048`
- Suggested screenshot filename: `07-run-history-dark.png`
- Suggested HTML filename: `07-run-history-dark.html`
- Screenshot file resource: `projects/16481042039965443151/files/318ae237c3504adfa777b29aa972ee0a`
- HTML file resource: `projects/16481042039965443151/files/e683006158514b85bb6f8c71587b4fd6`
- Screenshot URL: `https://lh3.googleusercontent.com/aida/ADBb0uh1rmx7sTJnNQY0ZU_D29QryYq6r4INXDksW7uaVtUwJFsjlTQKd3ziOjhyJPp4if7Dh_fspmofFKo-Lbs4lrsaSIp2ftvVn92FdXk6jj1JXywwCL7NM2Ge9yMV4vU-4anpWjgrSEt4v0OZNK3A611TzG7ROS8ZZyNNHdU78WvHBI4-YsUAo4u8cCaQ6jsoVvTz2hvfYYJcMQDFEl4kUThG5Ty0PDqfWHcYHdw2iwckMYpIX7to5kec9nU`
- HTML URL: `https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ8Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpbCiVodG1sX2JjNmVlMWY5ZTgzYzQ4MWZhYzE5YzA4YjY3MzI4OTE4EgsSBxCd6OLZ-h4YAZIBJAoKcHJvamVjdF9pZBIWQhQxNjQ4MTA0MjAzOTk2NTQ0MzE1MQ&filename=&opi=89354086`

## Optional Context Screens

These were present in the Stitch project but were not part of the requested screen list. They can be ignored for M16.1 unless a future UI task needs alternatives.

| Title | Screen ID |
|---|---|
| Taurus Run Overview | `737f7cfd7f4d4538976aadd6c4be2c5b` |
| Taurus Run Overview (Dark) | `296d29f9d7dc45228c47c1cf7e0cf428` |
| Taurus Run Overview (Dark) - v2 duplicate | `37f40acf51294c4ea12a471588bfbe74` |
| Run Detail: pr-20231027-01 | `c0a0c0b44de941fc9289086c5f4365db` |
| Run Detail: pr-20231027-01 (Dark) | `6b58fb2ecba04c6a93a7d5db467b327b` |
| INFY Decision Trail | `42c3a2c5f969470e876622f49af738c2` |
| INFY Decision Trail (Dark) | `04c3e6f64a104063b82ef9e7322088ba` |
| Taurus Risk Engine | `7ec1a5ef2d464596ae02656ed9eb2567` |
| Taurus Portfolio & Account | `b0f541d3f6fd4ef5aed643bd9cf3e257` |
| Taurus Screen List and IA | `fd0ec11386d54d27b4b10c13ba1c6953` |
| Historical Taurus UI design brief | `16568500018022921690` |
