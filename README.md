# Globoplay M3U v3

Versão otimizada para o GitHub Actions. A coleta usa até 5 páginas em paralelo, timeout curto por canal e valida somente manifests HLS (`#EXTM3U`) ou DASH (`<MPD>`). URLs de callback da API Globovideos são rejeitadas.

Atualiza a cada 6 horas. Se nenhuma URL reproduzível for encontrada numa execução, a playlist anterior é preservada.

`actions/checkout@v5` elimina o aviso antigo do checkout relacionado ao Node 20. O projeto não contorna login, DRM, assinatura ou bloqueios do Globoplay.
