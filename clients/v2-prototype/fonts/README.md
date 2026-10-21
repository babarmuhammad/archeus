# Fonts (V2 prototype)

Self-hosted OFL fonts. No CDN, no web font service at run time. Files are untrusted data: their sha256 values were checked against the bake-off manifest (D:\fontbake\manifest.csv) before copying.

| File | Family | Use on the Now frame | Upstream | Licence | sha256 |
|---|---|---|---|---|---|
| LibreCaslonText-wght.ttf | Libre Caslon Text, variable wght 400 to 700 | headline (37.42 px, +1.08 px tracking, weight 500), lede, mission and project titles, ARCHEUS wordmark, rail wordmark | https://github.com/google/fonts/tree/main/ofl/librecaslontext | SIL OFL 1.1, OFL-LibreCaslonText.txt | see sha256.txt |
| SourceSans3-wght.ttf | Source Sans 3, variable wght 200 to 900 | sans: state words, chat rows, composer, nav, status, header controls | https://github.com/google/fonts/tree/main/ofl/sourcesans3 | SIL OFL 1.1, OFL-SourceSans3.txt | see sha256.txt |

Choice: serif from the font bake-off (no free face matched the concept serif closely; Libre Caslon Text 500 was the owner's decision). Sans: Source Sans 3 400 over Inter, by shape IoU at width-solved sizes (mean 0.418 against 0.382 for Inter, on 22 sans items). EB Garamond and Inter were removed in round 10f.

Verify: `sha256sum -c sha256.txt`.
