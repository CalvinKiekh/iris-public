# iris auf dem Pi: eine Bruecke, die ihre Sitzungen selbst beherbergt.
#
# Am Mac haengt die Bruecke an Terminal-Fenstern, in denen Claude Code schon
# laeuft. Auf dem Pi gibt es keine Fenster - hier startet die Bruecke Claude
# Code selbst, und das Telefon redet mit diesen Sitzungen wie mit jeder
# anderen. Dafuer muss beides im selben Bild liegen: Python fuer die Bruecke,
# Node fuer Claude Code.
#
# Bewusst Debian und nicht Alpine: Claude Code bringt native Teile mit, die
# gegen glibc gebaut sind, und musl kostet mehr Abende als das Bild an Platz
# spart.
FROM node:22-bookworm-slim

# git, weil eine Uebergabe ueber das Repository laeuft und eine Sitzung hier
# klonen und pushen koennen muss. ripgrep, weil Claude Code danach sucht.
# ca-certificates fuer TLS, tini als Init - ohne einen bleiben Zombies stehen,
# und Claude Code startet Unterprozesse am laufenden Band.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-cryptography \
        git openssh-client ca-certificates curl ripgrep less tini \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code && npm cache clean --force

# Die GitHub-Kommandozeile. SSH allein reicht nicht: klonen und pushen geht
# damit, aber Repos auflisten, suchen, anlegen oder ein Issue schreiben nicht.
# Eine Sitzung auf diesem Rechner musste bis zum 28.09. beim Menschen
# nachfragen, wie ein Repo heisst - fuer den Rechner, der immer laeuft und
# von unterwegs bedient wird, ist das der falsche Weg herum.
# Feste Version, damit ein Neubau nicht stillschweigend etwas anderes holt.
ARG GH_VERSION=2.101.0
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${arch}.tar.gz" \
      | tar xz -C /tmp; \
    mv "/tmp/gh_${GH_VERSION}_linux_${arch}/bin/gh" /usr/local/bin/gh; \
    rm -rf /tmp/gh_*; \
    gh --version | head -1

# Nicht als root arbeiten. Die UID ist fest, damit die Dateien im Arbeits-
# ordner auf dem Pi nicht jedem Neubau gehoeren.
#
# Das Zuhause ist /arbeit, und zwar in der passwd-Datei selbst - nicht nur in
# $HOME. OpenSSH loest `~` ueber getpwuid auf und ignoriert $HOME dabei; mit
# /home/iris in der passwd suchte ssh seine config und known_hosts dort und
# fand nichts, obwohl beides unter /arbeit/.ssh lag. Dieselbe Falle hatte
# vorher schon git (daher dessen core.sshCommand mit vollem Pfad). So braucht
# niemand mehr ein -F oder einen absoluten Pfad, damit ein Sprung klappt.
RUN useradd -m -u 1001 -s /bin/bash -d /arbeit iris
WORKDIR /opt/iris

# Der Code der Bruecke wird beim Ausrollen hineingelegt, nicht eingebacken:
# er aendert sich taeglich, das Bild nicht.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    IRIS_HOME=/arbeit

# Git fuer ein zweites GitHub-Konto, z. B. das der Arbeit - wenn es eins
# gibt. Welches, steht in rechner.env (IRIS_GITHUB_ARBEIT) und kommt als
# Build-Argument herein; leer heisst: nur ein Konto, keine Umschreibung.
# Der zugehoerige SSH-Name `github-arbeit` steht in ~/.ssh/config auf dem
# Wirt, nicht hier.
#
# Der Schluessel entscheidet, welches Konto
# gilt, und `gh repo clone` kennt den Alias `github-arbeit` nicht - ohne diese
# Umschreibung landet jeder Griff nach einem Arbeitsrepo auf dem privaten
# Schluessel und liest sich als "Repository not found". Systemweit, damit es
# ein neues /arbeit uebersteht: die Konfiguration ist Einrichtung, keine
# Arbeitsdatei.
#
# Ausdruecklich KEIN core.sshCommand. Genau das stand hier vorher und band
# jede git-Aktion an den alten Deploy-Key, der nur iris darf - die
# ssh-Konfiguration wurde dabei komplett uebergangen, und alles ausser iris
# sah aus wie nicht vorhanden. Die Kruecke stammte daher, dass ssh das
# Zuhause des Nutzers nicht fand; das steht seit dem 28.09. richtig in der
# passwd.
ARG GITHUB_ARBEIT=
RUN if [ -n "$GITHUB_ARBEIT" ]; then \
      git config --system url."git@github-arbeit:${GITHUB_ARBEIT}/".insteadOf "git@github.com:${GITHUB_ARBEIT}/" \
   && git config --system --add url."git@github-arbeit:${GITHUB_ARBEIT}/".insteadOf "https://github.com/${GITHUB_ARBEIT}/"; \
    fi

EXPOSE 8780
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python3", "-m", "bridge", "--host", "0.0.0.0", "--port", "8780"]
