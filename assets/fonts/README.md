# Fontes

Vazio de propósito. Os PDFs usam a **DejaVuSans**, procurada nesta ordem:

1. `assets/fonts/DejaVuSans.ttf` (aqui)
2. Caminhos do sistema (`/usr/share/fonts/truetype/dejavu/…`)

No Streamlit Community Cloud a fonte é instalada pelo `packages.txt`
(`fonts-dejavu-core`). Se por algum motivo ela não estiver disponível, o app
**não quebra**: cai para Helvetica e remove os acentos dos PDFs.

Para garantir a acentuação em qualquer ambiente, baixe `DejaVuSans.ttf` e
`DejaVuSans-Bold.ttf` de https://dejavu-fonts.github.io/ e coloque nesta pasta.
