# Fonts (V2 prototype)

Self-hosted OFL fonts. No CDN, no web font service at run time.

| File | Family | Upstream | Licence | sha256 |
|---|---|---|---|---|
| EBGaramond-wght.ttf | EB Garamond, variable wght 400 to 800 | https://github.com/google/fonts/tree/main/ofl/ebgaramond (copied from raw.githubusercontent.com/google/fonts/main/ofl/ebgaramond/) | SIL OFL 1.1, OFL-EBGaramond.txt | see sha256.txt |
| Inter-wght-opsz.ttf | Inter, variable opsz 14 to 32 and wght 100 to 900 | https://github.com/google/fonts/tree/main/ofl/inter (copied from raw.githubusercontent.com/google/fonts/main/ofl/inter/) | SIL OFL 1.1, OFL-Inter.txt | see sha256.txt |

Downloaded from the official google/fonts repository on 2026-10-22 and treated as untrusted data: the files were checked for their family names and axes with fontTools, not executed. The serif is EB Garamond, chosen over Cormorant Garamond by overlaying the concept headline (the concept has lining figures and a heavier stroke; EB Garamond gave the higher ink overlap, 0.40 against 0.34 for Cormorant at matched width).

Verify: `sha256sum -c` against sha256.txt (sha256sum format: hash, two spaces, name).
