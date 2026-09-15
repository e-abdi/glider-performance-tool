# Glider Performance Tool

Research compendium for comparing how the PAM-equipped gliders of the NOAA Fisheries
Glider Rodeo 2026 performed across mission modes (fast, slow, intermediate, drift):
piloting, navigation, endurance and self-noise.

## Link to Final Report
**TODO: link to the project website once GitHub Pages is on**

## How to Cite
**TODO: recommended citation**

## Research Compendium
This repository contains the code, documentation and small derived outputs for the
Glider Performance Tool. It follows the
[Glider Rodeo Hackweek Projects research compendium template](https://github.com/NMFS-PAM-Glider/GliderRodeo-HackweekProjects).

## Contents

-   📁 content: pages for the project website (Quarto)
-   📁 code: scripts and modules that do the analysis
-   📁 data: pointers to the ORIGINAL data (no large files in git)
-   📁 output: modified or intermediate data products made by the code
-   📁 supplement: supplementary files that are not data, code or website pages
-   📄 index.qmd, _quarto.yml: website home page and configuration
-   📄 requirements.txt: Python packages

## Getting started

```bash
git clone https://github.com/e-abdi/glider-performance-tool.git
cd glider-performance-tool
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Input data: the Glider Rodeo deployment data, on the Glider Rodeo JupyterHub in
`~/shared-public/GliderRodeo`. See [data/ReadMe.md](data/ReadMe.md).

## Collaborators
Ehsan Abdi, Akvaplan-niva, eab@akvaplan.niva.no

## Funding
**TODO: statement of funding**

## Acknowledgements
This project was part of the Glider Rodeo Hackathon, which worked with PAM-Glider data collected
by the NOAA Fisheries Glider Rodeo (2026). The event was hosted by NOAA Fisheries with support
from Openscapes (JupyterHub, support), Oregon State University (Zoom, Box data storage) and
Aquaview (technical support).

## License
Released under CC0 1.0 Universal (see [LICENSE](LICENSE)), as in the template.
