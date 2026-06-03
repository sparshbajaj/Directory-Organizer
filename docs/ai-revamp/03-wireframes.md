# TUI Wireframes (ASCII)

## Home / Config
+----------------------------------------------------------+
| Download Organizer                                       |
| Folder: [D:\Downloads________________________] [Browse] |
| AI: [Enabled]  Provider: [Custom]  Model: [minimax...]   |
| Batch: [1]  Pause(ms): [300]  Dry Run: [Yes]             |
|                                                          |
| [Start Scan]  [History]  [Settings]                      |
+----------------------------------------------------------+

## Scan Progress
+----------------------------------------------------------+
| Scanning...  1240 / 5321 files                           |
| Current: report-2024-final.pdf                           |
| AI: analyzing (timeout 20s)                              |
|                                                          |
| [View Log]                                               |
+----------------------------------------------------------+

## Suggestions List
+----------------------------------------------------------+
| Suggestions (Filter: All | Rename | Move | No Change)    |
|----------------------------------------------------------|
| [ ] invoice_01.pdf  ->  2024-01_invoice_acme.pdf         |
| [x] photo1.jpg      ->  2023-07_trip_photo1.jpg          |
| [ ] setup.exe       ->  (no change)                      |
| ...                                                      |
|----------------------------------------------------------|
| Details | Map | Apply Selected | Export Preview          |
+----------------------------------------------------------+

## Suggestion Detail
+----------------------------------------------------------+
| File: invoice_01.pdf                                     |
| Suggested: 2024-01_invoice_acme.pdf                       |
| Move to: Finance/Invoices/2024/                          |
| Confidence: 0.84   Risk: Low                             |
| Rationale: detected vendor "Acme" and month in text      |
| [Approve] [Skip] [Edit]                                  |
+----------------------------------------------------------+

## Map View
+----------------------------------------------------------+
| Map: Cluster "Project-X" (12 files)                      |
|----------------------------------------------------------|
|   [report_v2.docx]---[slides_final.pptx]                 |
|          |                 |                              |
|   [budget.xlsx]     [assets.zip]                         |
|                                                          |
| [Open Cluster] [Back to List]                            |
+----------------------------------------------------------+
