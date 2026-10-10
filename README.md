# Synapse Workflow Companion

A static, CSV-driven telestroke workflow companion.

## Project structure

- `index.html` — lightweight application shell
- `css/styles.css` — presentation and responsive layout
- `js/app.js` — UI state, drag-and-drop import, and rendering
- `js/guideline-parser.js` — CSV parsing and browser-local import storage
- `js/nudges.js` — editable alert/nudge rules and guided-action availability
- `guidelines/` — the seven bundled hospital CSVs and `manifest.json`

## Add a hospital without code

On the website, drag a guideline CSV into **Add a hospital guideline**, or use the file picker. The importer expects a two-column CSV with a header row such as:

```csv
Guide Field,Synthetic Value
Local Time Zone,Eastern (America/New_York)
Thrombolytic,Tenecteplase
LVO Protocol,…
```

Imports are stored in the browser that uploaded them. They do not change the shared site for other people. To make a guideline part of the shared public site, add its CSV under `guidelines/` and add its name, SYN ID, and filename to `guidelines/manifest.json` in a pull request.

## Collaborating on nudges

The dedicated file for alert/nudge wording and logic is [js/nudges.js](js/nudges.js). Team members can branch, edit that file, and open a pull request without touching the importer or layout.

GitHub Pages deploys changes merged to `main` automatically.
