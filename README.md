# 🎨 arte_do_dia.py

Script em Python que busca a **"Obra de arte do dia"** do [Google Arts & Culture](https://artsandculture.google.com/) e a envia por **e-mail todos os dias**, com a **imagem em anexo** e os **dados da obra e do artista** no corpo da mensagem.

---

## Sumário

- [O que é o Google Arts & Culture](#o-que-é-o-google-arts--culture)
- [O que o script faz](#o-que-o-script-faz)
- [Dados incluídos no e-mail](#dados-incluídos-no-e-mail)
- [Como funciona (passo a passo)](#como-funciona-passo-a-passo)
- [Requisitos e instalação](#requisitos-e-instalação)
- [Configuração](#configuração)
- [Uso e opções de linha de comando](#uso-e-opções-de-linha-de-comando)
- [Agendamento diário](#agendamento-diário)
- [Arquivos gerados](#arquivos-gerados)
- [Solução de problemas](#solução-de-problemas)
- [Limitações e avisos](#limitações-e-avisos)

---

## O que é o Google Arts & Culture

O **Google Arts & Culture** é uma plataforma online gratuita do Google que reúne, em um só lugar, acervos de **museus, galerias, arquivos e instituições culturais do mundo todo**. Nasceu em 2011 como *Google Art Project* e hoje também está disponível em aplicativo (Android e iOS) e em uma extensão para o Chrome.

A função do site é **democratizar o acesso à arte e à cultura**, permitindo que qualquer pessoa explore obras e lugares sem sair de casa. Entre os recursos principais:

| Recurso | Para que serve |
|---|---|
| **Obras de arte em alta resolução** | Imagens com zoom extremo (inclusive "gigapixel", capturadas por câmeras próprias do projeto), que permitem ver pinceladas e detalhes impossíveis a olho nu. |
| **Fichas das obras** | Cada obra tem página própria com título, criador, datas, técnica, dimensões, proveniência, etiquetas e informações sobre o artista. |
| **Páginas de artistas e entidades** | Biografia e obras relacionadas a artistas, movimentos, técnicas e instituições. |
| **Visitas virtuais (Street View)** | Passeios pelo interior de museus e monumentos. |
| **Histórias e exposições online** | Conteúdo editorial criado por especialistas e pelos parceiros culturais. |
| **Experimentos** | Ferramentas interativas como *Art Selfie* (encontrar obras parecidas com seu rosto) e *Art Transfer* (aplicar o estilo de uma obra às suas fotos). |
| **Obra de arte do dia** | Destaque diário da página inicial — é essa a obra que este script entrega por e-mail. |

> O Google Arts & Culture **não oferece uma API pública** para a obra do dia. Por isso o script lê as páginas do próprio site (veja [Limitações](#limitações-e-avisos)).

---

## O que o script faz

1. Descobre qual é a **obra de arte do dia** na página inicial do Google Arts & Culture (em português do Brasil).
2. Abre a página da obra e **extrai os metadados** (título, criador, vida, nacionalidade etc.).
3. **Baixa a imagem** da obra em alta resolução (lado maior de 2048 px).
4. Monta um **e-mail em texto e HTML** com os dados e a imagem **anexada**.
5. **Envia** o e-mail via SMTP (padrão: Gmail) para um ou mais destinatários.
6. Registra o envio para **não repetir** no mesmo dia.

### Funcionalidades em resumo

- ✅ Envio diário automatizável (cron, systemd, Agendador de Tarefas etc.).
- ✅ Imagem da obra **anexada** em alta resolução, com nome de arquivo derivado do título.
- ✅ E-mail **multipart**: versão em texto simples + versão HTML formatada em tabela.
- ✅ Suporte a **vários destinatários** (separados por vírgula).
- ✅ **Proteção contra duplicidade**: não envia duas vezes no mesmo dia (a menos que use `--force`).
- ✅ **Modo de teste** (`--dry-run`): não envia nada e salva uma prévia local.
- ✅ **Modo de depuração** (`--debug-home`): salva o HTML da página inicial para diagnóstico.
- ✅ **Fallback automático** para navegador renderizado (Playwright) quando a página inicial não traz o link no HTML estático.
- ✅ Possibilidade de **forçar uma obra específica** (`--url` ou variável `ASSET_URL`).
- ✅ Configuração por variáveis de ambiente ou arquivo `.env`.
- ✅ Em caso de falha, **não envia uma obra errada**: encerra com erro e mensagem explicativa (ideal para logs de cron).

---

## Dados incluídos no e-mail

O corpo da mensagem traz, nesta ordem:

| Campo | Descrição |
|---|---|
| **Título** | Nome da obra |
| **Criador** | Artista/autor |
| **Vida do criador** | Anos de nascimento e morte |
| **Nacionalidade do criador** | Ex.: flamengo, brasileiro |
| **Sexo do criador** | Conforme a ficha da obra |
| **Local de nascimento do criador** | Cidade/país |
| **Local da morte do criador** | Cidade/país |
| **Dimensões físicas** | Altura × largura etc. |
| **Etiquetas** | Palavras-chave associadas à obra |
| **Proveniência** | Histórico de propriedade da obra |
| **Informações sobre o artista** | Pequena biografia da ficha |
| **Pintor** | Nome do pintor (quando informado) |
| **Tipo** | Tipo de objeto (ex.: pintura) |
| **Link externo** | Link para fonte externa da instituição, quando existir |

Campos que a ficha da obra **não possui** aparecem como `—`. Ao final, o e-mail inclui o link para a página da obra no Google Arts & Culture.

**Assunto do e-mail:** `🎨 Obra de arte do dia (DD/MM/AAAA): <Título>`

---

## Como funciona (passo a passo)

```
┌──────────────────────┐
│ Home do Google A&C   │  hl=pt-BR
└──────────┬───────────┘
           │ 1. localiza o bloco "Obra de arte do dia"
           │    (HTML estático; se falhar → Chromium/Playwright)
           ▼
┌──────────────────────┐
│ Página /asset/...    │
└──────────┬───────────┘
           │ 2. lê os pares "Rótulo: valor" da ficha
           │    + og:title / og:image como reserva
           ▼
┌──────────────────────┐
│ Imagem (=s2048)      │  3. download da imagem
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ E-mail (texto+HTML)  │  4. anexo + tabela de dados
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ SMTP (STARTTLS)      │  5. envio + registro do dia
└──────────────────────┘
```

**Detalhes importantes da descoberta da obra:** o script procura o título do bloco ("Obra de arte do dia" / "Artwork of the Day") **somente no conteúdo visível da página**, ignorando `<script>` e `<style>` (onde o mesmo texto aparece em strings de tradução e levaria a uma obra errada). Depois pega o primeiro link `/asset/...` que vem após esse título.

**Rótulos bilíngues:** os campos são reconhecidos tanto em português quanto em inglês (ex.: "Vida do criador" / "Creator Lifespan"), então o script continua funcionando se o site responder em outro idioma.

---

## Requisitos e instalação

- Python **3.10+**
- Acesso à internet e a um servidor SMTP

```bash
pip install requests beautifulsoup4
```

**Recomendado** (a página inicial do Google é muito dinâmica e normalmente precisa de renderização):

```bash
pip install playwright
playwright install chromium
```

> Em servidores Linux sem interface gráfica, o Chromium do Playwright pode exigir bibliotecas do sistema. Se necessário: `playwright install-deps chromium`.

---

## Configuração

Crie um arquivo **`.env`** na mesma pasta do script (ou defina as variáveis no ambiente):

```ini
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=seu@gmail.com
SMTP_PASS=sua_senha_de_app
MAIL_FROM=seu@gmail.com
MAIL_TO=destino1@exemplo.com,destino2@exemplo.com
```

| Variável | Obrigatória | Padrão | Descrição |
|---|---|---|---|
| `SMTP_HOST` | não | `smtp.gmail.com` | Servidor SMTP |
| `SMTP_PORT` | não | `587` | Porta (usa STARTTLS) |
| `SMTP_USER` | **sim** | — | Usuário SMTP |
| `SMTP_PASS` | **sim** | — | Senha SMTP |
| `MAIL_FROM` | não | `SMTP_USER` | Remetente |
| `MAIL_TO` | **sim** | — | Destinatário(s), separados por vírgula |
| `ASSET_URL` | não | — | Força uma obra específica (ignora a descoberta automática) |

**Gmail:** use uma **senha de app** (exige verificação em duas etapas), criada em <https://myaccount.google.com/apppasswords>. Não use a senha normal da conta.

**Segurança:** proteja o arquivo de credenciais e não o envie ao Git.

```bash
chmod 600 .env
echo ".env" >> .gitignore
echo ".arte_do_dia_state.json" >> .gitignore
echo "preview/" >> .gitignore
```

---

## Uso e opções de linha de comando

```bash
python3 arte_do_dia.py [opções]
```

| Opção | Efeito |
|---|---|
| *(nenhuma)* | Busca a obra do dia e envia o e-mail (se ainda não enviou hoje). |
| `--dry-run` | **Não envia.** Imprime os campos no terminal e salva a imagem e o e-mail (`.eml`) em `./preview/`. |
| `--force` | Envia mesmo que já tenha enviado hoje. |
| `--url <URL>` | Usa uma página `/asset/...` específica em vez da obra do dia (útil para testar a extração). |
| `--debug-home` | Salva `home_static.html` e `home_rendered.html` em `./preview/` e mostra qual obra cada método detectou. |

### Exemplos

```bash
# Testar sem enviar
python3 arte_do_dia.py --dry-run

# Enviar agora, mesmo já tendo enviado hoje
python3 arte_do_dia.py --force

# Testar a extração de metadados de uma obra específica
python3 arte_do_dia.py --dry-run --url "https://artsandculture.google.com/asset/tQGnUrSWVGpvnw"

# Diagnosticar a detecção da obra do dia
python3 arte_do_dia.py --debug-home
```

**Código de saída:** `0` em caso de sucesso (ou se já enviou hoje) e `1` em caso de erro, com a mensagem em `stderr`.

---

## Agendamento diário

### Cron (Linux/macOS)

```cron
# Todo dia às 08:00
0 8 * * * cd /caminho/do/script && /usr/bin/python3 arte_do_dia.py >> arte_do_dia.log 2>&1
```

### systemd timer (alternativa)

`/etc/systemd/system/arte-do-dia.service`
```ini
[Unit]
Description=Envia a Obra de arte do dia por e-mail

[Service]
Type=oneshot
WorkingDirectory=/caminho/do/script
ExecStart=/usr/bin/python3 /caminho/do/script/arte_do_dia.py
```

`/etc/systemd/system/arte-do-dia.timer`
```ini
[Unit]
Description=Agenda diária da Obra de arte do dia

[Timer]
OnCalendar=*-*-* 08:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now arte-do-dia.timer
```

> `Persistent=true` executa o envio assim que a máquina ligar caso o horário tenha sido perdido. A trava diária impede duplicidade.

---

## Arquivos gerados

| Arquivo | Descrição |
|---|---|
| `.arte_do_dia_state.json` | Guarda a data e o ID da última obra enviada (evita envio duplicado). |
| `preview/imagem.jpg` | Imagem baixada (apenas em `--dry-run`). |
| `preview/email.eml` | E-mail completo gerado, abrível em qualquer cliente de e-mail (apenas em `--dry-run`). |
| `preview/home_static.html` | HTML estático da página inicial (apenas em `--debug-home`). |
| `preview/home_rendered.html` | HTML da página inicial após renderização no navegador (apenas em `--debug-home`). |
| `arte_do_dia.log` | Log do cron, se redirecionado como no exemplo. |

---

## Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `Não consegui localizar a 'Obra de arte do dia'` | A home não traz o bloco no HTML estático e o Playwright não está instalado. | Instale o Playwright (veja acima) e rode `--debug-home`. |
| Veio uma obra diferente da exibida no site | O layout da home mudou. | Rode `--debug-home` e inspecione os HTMLs salvos; use `--url` ou `ASSET_URL` como solução provisória. |
| Campos aparecendo como `—` | O rótulo na página é diferente do esperado ou a obra não tem o dado. | Confira a ficha no site e ajuste os apelidos na lista `FIELDS` do script. |
| `SMTPAuthenticationError` | Senha incorreta ou conta sem senha de app. | Gere uma senha de app e use-a em `SMTP_PASS`. |
| `Variável SMTP_USER não definida` | `.env` ausente ou em outra pasta. | O `.env` deve ficar ao lado do script (ou exporte as variáveis). |
| Nada acontece ("Já enviado hoje") | A trava diária foi acionada. | Use `--force` ou apague `.arte_do_dia_state.json`. |
| E-mail cai no spam | Remetente/servidor sem reputação. | Use um SMTP confiável e marque a mensagem como "não é spam" na primeira vez. |

---

## Limitações e avisos

- **Sem API oficial.** O script depende da estrutura atual das páginas do Google Arts & Culture. Se o Google mudar o layout, a detecção da obra do dia ou a leitura dos campos podem precisar de ajuste.
- **Campos variáveis.** Cada instituição preenche a ficha da obra como quer; é normal que alguns campos (proveniência, dimensões, pintor etc.) venham vazios.
- **Direitos de imagem.** As imagens pertencem às instituições parceiras e aos respectivos detentores de direitos. Use o script para **fins pessoais** e consulte os termos do Google Arts & Culture antes de redistribuir o conteúdo.
- **Uso responsável.** O script faz poucas requisições por dia (uma à home e uma à página da obra). Evite executá-lo em intervalos curtos.
- **Tamanho do anexo.** A imagem em 2048 px costuma ficar entre 1 e 5 MB, bem abaixo do limite de 25 MB do Gmail. Para reduzir, altere `IMAGE_SIZE` no topo do script (ex.: `s1280`).
