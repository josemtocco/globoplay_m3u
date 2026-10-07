# Globoplay M3U v2 — SS IPTV

Versao corrigida do projeto. A versao anterior gravava um callback `api.globovideos.com/.../playlist/without_resources/callback/...`, que nao e um stream HLS reproduzivel.

Esta versao:
- descobre paginas de canais no catalogo do Globoplay;
- tambem inclui os canais atualmente listados pelo catalogo como fallback;
- intercepta a rede do navegador e performance entries;
- rejeita callbacks da API e URLs que nao sejam `.m3u8`/`.mpd`;
- verifica o manifesto antes de gravar na M3U;
- atualiza a cada 6 horas;
- se nenhuma fonte valida for encontrada, preserva a playlist anterior;
- gera nomes e `group-title` no M3U.

O projeto nao tenta contornar login, DRM, assinatura ou bloqueio regional. Somente streams que o site disponibilizar ao navegador e que retornarem um manifesto valido entram na lista.

Playlist apos o primeiro workflow:
`https://raw.githubusercontent.com/SEU_USUARIO/SEU_REPOSITORIO/main/lista.m3u`
