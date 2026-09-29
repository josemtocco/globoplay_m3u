# Globoplay → M3U para SS IPTV

Projeto automatizado para gerar `lista.m3u` a partir dos **canais que o catálogo público do Globoplay disponibilizar ao navegador**.

Fonte principal:

```text
https://globoplay.globo.com/catalogo/
```

## O que esta versão faz

- Varre automaticamente o catálogo do Globoplay.
- Descobre as páginas públicas de canais (`/canais/`).
- Para cada canal, abre a página no Chromium via Playwright.
- Captura somente URLs de mídia que o próprio site expõe ao navegador, como HLS (`.m3u8`) ou DASH (`.mpd`).
- Gera `lista.m3u` na raiz do repositório.
- Usa `group-title` com o nome do canal, mantendo a separação por canal exibida no catálogo.
- Mantém somente streams encontrados na atualização atual.
- Remove streams/canais que deixaram de ser encontrados.
- Acrescenta automaticamente canais novos que aparecerem no catálogo.
- Preserva a última lista válida se houver uma falha transitória de rede ou do Globoplay.
- Executa automaticamente a cada 6 horas pelo GitHub Actions.
- Faz commit somente quando `lista.m3u` ou `channels.json` mudarem.

## Canais

O catálogo atual do Globoplay publica, entre outros, TV Globo, Multishow, GloboNews, sportv, GNT, Globoplay Novelas, Gloob, Canal Brasil, Canal OFF e Modo Viagem, além de Premiere na área de parceiros. A lista é descoberta dinamicamente pelo scraper, portanto não precisa ser codificada manualmente. 

## Importante sobre acesso

O projeto **não** tenta contornar:

- DRM;
- login;
- assinatura/pagamento;
- geoblocking;
- tokens protegidos;
- controles de acesso do Globoplay.

Se determinado canal exigir autenticação, assinatura ou não expuser um stream utilizável para uma sessão pública do navegador, ele não será transformado artificialmente em uma URL M3U.

As URLs de mídia podem ser temporárias. Por isso a lista é regenerada a cada 6 horas.

## Estrutura

```text
.
├── .github/
│   └── workflows/
│       └── atualizar-m3u.yml
├── channels.json
├── lista.m3u
├── requirements.txt
├── scraper.py
├── .gitignore
└── README.md
```

Todos os arquivos funcionais, incluindo `lista.m3u`, ficam na raiz. A única exceção estrutural é o workflow do GitHub Actions, que obrigatoriamente fica em `.github/workflows/`.

## Instalação no GitHub

1. Crie um repositório no GitHub.
2. Envie todos os arquivos deste projeto para a raiz.
3. Vá em **Settings → Actions → General** e confirme que Actions está habilitado.
4. Vá em **Actions → Atualizar lista M3U**.
5. Execute **Run workflow** manualmente na primeira vez.
6. O workflow continuará rodando a cada 6 horas.

## URL para SS IPTV

Depois da primeira execução, use o endereço Raw de `lista.m3u`:

```text
https://raw.githubusercontent.com/SEU-USUARIO/SEU-REPOSITORIO/main/lista.m3u
```

Exemplo:

```text
https://raw.githubusercontent.com/bepi/meu-globoplay-m3u/main/lista.m3u
```

## Execução local

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Depois:

```bash
pip install -r requirements.txt
python -m playwright install chromium
python scraper.py --verbose
```

## Frequência

O workflow usa:

```text
0 */6 * * *
```

Isso significa uma execução a cada 6 horas em UTC. O GitHub pode iniciar o job alguns minutos depois do horário previsto devido à fila de execução.

## Atualização da lista

A cada execução:

1. o catálogo é consultado;
2. os canais publicados são identificados;
3. cada página de canal é aberta;
4. os streams expostos são coletados;
5. URLs duplicadas são eliminadas pela URL canônica;
6. streams encontrados entram na nova lista;
7. streams que não aparecem mais são removidos;
8. novos streams entram automaticamente;
9. `channels.json` e `lista.m3u` são gravados;
10. o GitHub Actions faz commit somente se houver alteração.

Se o catálogo ou o Globoplay estiver temporariamente indisponível, a execução não apaga uma lista válida já existente.
