# Contributing

Thanks for helping. The tool is only as good as the numbers in it, so corrections from people
who fly these gliders are the most valuable contribution there is.

## Ways to help

- **Report a problem or a wrong number.** Open an
  [issue](https://github.com/e-abdi/glider-performance-tool/issues), or use the *Report an issue*
  link on any page of the website. Say which page, what you saw, what you
  expected, and where the right value comes from.
- **Fix something small.** Every page has an *Edit this page* link, which opens the source on
  GitHub. You can edit and propose the change from the browser, with nothing to install.
- **Add a glider, sensor or PAM recorder, or a new page.** Read
  [Where each page's data comes from](#where-each-pages-data-comes-from) first: some data is
  generated, and editing the generated copy is undone at the next rebuild.

## Ground rules for data

- **Every number needs a source.** That means a datasheet, a paper, a manual, or a deployment
  you flew. Put it in the `source` or note column where there is one, or in the commit message.
  A plausible number with no source is worse than a gap.
- **Say how sure you are.** If a value is an estimate or a vendor claim that has not been
  tested, say so on the page or in the data.
- **Don't name individual gliders on the endurance pages.** The Seaglider model is fitted to
  our own vehicle's logs, but the page describes the method, not the vehicle.

## Where each page's data comes from

Pages are Quarto files (`.qmd`). Most are HTML and JavaScript inside a ```` ```{=html} ````
block, so you edit them as you would a web page. Some pages hold a **generated block** between
two marker comments, such as `<!-- SENSOR-DATA:BEGIN -->` and `<!-- SENSOR-DATA:END -->`. A
script rewrites only what is between the markers. Edit anything else on the page directly, but
never the inside of a marked block.

| Page | Edit directly | Generated (don't edit by hand) | Generated from |
|---|---|---|---|
| Glider Selection Dashboard (`content/glider-selection.qmd`) | The glider list (`const GLIDERS = [...]`), the filters, the text | The `SENSOR-DATA` block | `code/build_sensor_data.py` ← the glider/PAM workbook in `output/`, plus `content/data/sensor-links.csv` |
| Direct Comparison (`content/direct-comparison.qmd`) | The layout and text around the table | The `COMPARISON-DATA` block | `code/build_comparison_data.py` ← `output/direct comparison.ods` (the words), plus `content/data/comparison-tags.csv` (which glider has the edge, and the topics) |
| Study Design Tool (`content/study-design.qmd`) | Everything | — | — |
| Slocum endurance (`content/slocum-endurance.qmd`) | **Nothing:** the whole page is generated | Whole file | `code/build_endurance_page.py` ← `content/data/endurance-model.json` and `content/data/extra-sensors.csv` |
| Seaglider endurance (`content/seaglider-endurance.qmd`) | Everything outside the markers (controls, labels, text) | The `SEAGLIDER-DATA` block | `code/build_seaglider_page.js` ← `content/data/seaglider-model.json` |
| Glider Performance (`content/performance.qmd`) | Everything outside the markers | The `PERF-DATA` block | `code/build_performance_data.py` ← `output/glider_performance_summary.xlsx` |

### Changes anyone can make, with no spreadsheet

These files are committed, and CI rebuilds the pages from them on every push:

- **Add an external sensor to the Slocum endurance page:** add one row to
  `content/data/extra-sensors.csv`. Its columns are explained in
  [content/data/ReadMe.md](content/data/ReadMe.md).
- **Change who has the edge in the Direct Comparison, or a factor's topics:** edit
  `content/data/comparison-tags.csv`, then run `python3 code/build_comparison_data.py`. This
  step needs the ODS file, so if you don't have it, open a pull request with only the CSV and a
  maintainer will run the script.
- **Add an integration link to a sensor on the dashboard:** edit
  `content/data/sensor-links.csv`. The same applies: a maintainer runs
  `code/build_sensor_data.py`.
- **Add or correct a glider on the dashboard:** edit its entry in `GLIDERS` in
  `content/glider-selection.qmd`. Copy an existing entry, and keep the `*Note` fields saying
  where each range comes from.

### Changes that need the source spreadsheets

The spreadsheets in `output/` are **not in the repository**. They are gitignored, either
because they are large or because they come from vendors. Changes to the words in the
comparison table, to the PAM and sensor specs, to the Slocum workbook model or to the rodeo
summary start in those files. Open an issue describing the change, and a maintainer who holds
them will make it.

If you do hold a copy, edit the workbook in Excel or LibreOffice. **Don't save it from
openpyxl:** the glider/PAM workbook has a threaded comment that openpyxl silently drops.

## Making a change

1. **Pull first:** `git pull --ff-only`. Several people edit the same pages, so start from the
   latest `main`.
2. **Preview the site:** `quarto preview`. The pages do their work in the browser, so click
   through what you changed. Also check the browser console for errors, and look at the page
   in dark mode.
3. **Run the checks** if you touched anything they cover. CI runs the same ones and refuses to
   publish if one fails:

   ```bash
   python3 code/build_endurance_page.py       # rebuild the Slocum page
   node code/check_extra_sensors.js           # extra-sensors.csv still matches the workbook's terms
   node code/check_endurance_model.js         # Slocum model reproduces the workbook exactly
   node code/build_seaglider_page.js --check  # Seaglider model still matches every logged mission
   ```

4. **Commit only your own files.** Stage files by name rather than with `git add -A`; the
   working tree often has rendered files and other people's work in it. Write a commit message
   that says what changed and why.
5. **Open a pull request** if you are not a maintainer, or push to `main` if you are. Then make
   sure the *Render and Publish* run in the
   [Actions tab](https://github.com/e-abdi/glider-performance-tool/actions) passed. If that run
   fails, the live site silently keeps serving the previous version, and the separate *pages
   build and deployment* run still shows green.

**Never run `quarto publish` from your own machine.** It overwrites the live site with whatever
your checkout has, regardless of what is on `main`. A stale local publish once deleted a whole
page and brought back removed ones. Publishing belongs to CI alone.

## Adding a page

1. Create `content/<name>.qmd`. Copy the front matter from an existing page; most use
   `page-layout: full` and `toc: false`.
2. Add it to the sidebar in `_quarto.yml`, and give it a line on the home page (`index.qmd`)
   and in the README's page table.
3. Scope the page's CSS under one wrapper id, as the other pages do (for example
   `#study-design .metric`), so it can't leak into the rest of the site. Define colours as CSS
   variables and redefine them for dark mode.
4. If the page fetches data from another site, that service has to allow cross-origin requests
   (`Access-Control-Allow-Origin`), because there is no server. Check with
   `curl -I -H 'Origin: https://e-abdi.github.io' <url>` before building on it. Credit the
   source on the page.
5. Load libraries from a CDN with a pinned version (for example `turf@7`, `plotly.js/2.35.3`),
   never an unversioned URL.

## Code conventions

- Scripts in `code/` start with a header saying what they do, how to run them, and what they
  read and write. Scripts that update a page change only the marked block, and refuse to run
  if the markers are missing.
- Python uses the packages in `requirements.txt`; Node scripts use only the standard library.
- Match the style of the file you are editing. The pages are deliberately plain JavaScript with
  no build step.

## Questions

Open an issue, or contact one of the team listed in the [README](README.md#team).
