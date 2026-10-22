# Fonts (vendored, SIL Open Font License 1.1)

Self-hosted OFL fonts. No CDN and no web font service at run time. Files are data: the browser reads them, nothing executes them.
Verify the files with `sha256sum -c sha256.txt`.

| File | Family | Used for | Upstream | Licence |
|---|---|---|---|---|
| `LibreCaslonText-VF.ttf` | Libre Caslon Text, variable wght 400 to 700 | the serif everywhere: headline (weight 500), lede, titles, wordmark, labels | https://github.com/google/fonts/tree/main/ofl/librecaslontext (`LibreCaslonText[wght].ttf`) | `OFL-LibreCaslonText.txt` |
| `SourceSans3-wght.ttf` | Source Sans 3, variable wght 200 to 900 | the sans on the desktop frame and the other views: state words, chat rows, composer, nav, status, header controls | https://github.com/google/fonts/tree/main/ofl/sourcesans3 | `OFL-SourceSans3.txt` |
| `Inter-VF.ttf` | Inter, variable (opsz pinned to 14, wght 100 to 900) | the sans on the phone Overview only (`Archeus Sans`), where it measured closer than Source Sans 3 | https://github.com/google/fonts/tree/main/ofl/inter (`Inter[opsz,wght].ttf`) | `OFL-Inter.txt` |
| `RobotoMono-wght.ttf` | Roboto Mono, variable wght 100 to 700 | the terminal (monospace) | https://github.com/google/fonts/tree/main/ofl/robotomono | `OFL-RobotoMono.txt` |

Choices. The serif comes from the font bake-off in `D:\fontbake\results.md` (no free face matched the concept serif; best mean IoU 0.47), and
the owner chose Libre Caslon Text 500. The sans is Source Sans 3 400 (shape IoU 0.418 against 0.382 for Inter on 22 sans items). Inter stays
only on the phone Overview, where the earlier overlay measured its mean error lower (23.2 against 24.9 for Source Sans 3).

Copyright: Libre Caslon Text, Source Sans 3 and Roboto Mono per their OFL 1.1 licence texts; Inter: Copyright 2020 The Inter Project Authors.
