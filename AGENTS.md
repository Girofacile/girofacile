# Flusso di lavoro del progetto

Per le modifiche richieste dall'utente, completare i controlli pertinenti,
creare un commit e fare push direttamente su `origin/main`, salvo diversa
indicazione nella richiesta. Non creare branch o pull request che richiedano
un'approvazione manuale per il normale flusso di lavoro.

Prima di iniziare, verificare lo stato locale e aggiornare i riferimenti remoti.
Preservare le modifiche altrui e sincronizzare main senza riscrivere la cronologia.
Includere nel commit soltanto i file pertinenti alla richiesta. Non ripristinare
modifiche annullate dall'utente e non usare force push.

Usare Git locale per commit e push. Confermare l'esito del caricamento e indicare
il commit nella risposta finale. Se autenticazione, protezioni del repository o
controlli impediscono il push, riportare il blocco senza dichiararlo completato.

## Più assistenti sullo stesso progetto

Claude Code e Codex lavorano su copie di lavoro separate dello stesso repository,
mai sulla stessa cartella:

- `Documents\girofacile`: Claude Code;
- `Documents\girofacile-codex`: Codex (ramo locale `lavoro-codex`, che segue `origin/main`).

Regole per entrambi:

- Lavorare solo nella propria cartella; non leggere, modificare, ripristinare o
  sincronizzare i file della cartella dell'altro.
- Prima di iniziare: `git fetch origin` e allineare la propria copia a `origin/main`
  solo se non ci sono modifiche locali non salvate in un commit
  (`git merge --ff-only origin/main`). Mai `git reset --hard`, `git checkout --` o
  `git clean` su modifiche che non sono le proprie.
- Alla fine: commit e push subito, nella stessa operazione, con
  `git push origin HEAD:main`. Se il push viene rifiutato perché `main` è avanzato,
  aggiornare con `git fetch origin` e `git rebase origin/main` sui propri commit non
  ancora pubblicati, ripetere i controlli e riprovare; mai force push.
