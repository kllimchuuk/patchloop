# Sedenie 02: správa o práci

**Etapa:** pieskovisko (SPEC §14, krok 2): príprava obrazu, spustenie bez siete, limity, zachytenie výstupu
**Úloha:** `docs/prompts/02-sandbox.md`
**Dátum:** 26. 10. 2026 · **Vykonávateľ:** Claude Code (Sonnet 5.5)

```
ZVIT 27. 10. 2026 — Sedenie 02, pieskovisko
Hotovo: balík sandbox/ (workspace.py, image.py, runner.py, errors.py), sekcia sandbox v konfigurácii,
        závislosť docker, značka pytest docker; opravy po dvoch code review (rozhodnutia 22 a 23).
Čísla: 57 testov bežne (0,17 s), 10 testov s -m docker (5,8 s), ruff bez chýb; zostavenie obrazu
       (python:3.12-slim + jedna závislosť, základný obraz už stiahnutý) 2,1 s, opakované volanie
       z cache 0,02 s; beh kontajnera s importom nainštalovanej závislosti 0,08–0,10 s (5 behov,
       s init a read-only koreňom); po behoch 0 zvyšných kontajnerov.
Odchýlky od SPEC: žiadne (SPEC §12 doplnená o pravidlo pre pracovnú kópiu a .env)
Potrebné rozhodnutie: (a) v kroku 3 určiť, ako sa nainštaluje samotný projekt (pip install .):
       fáza 1 kopíruje len manifesty, takže potrebuje zdrojáky; (b) základný obraz: SPEC uvádza
       python:3.12 (~1 GB), testy používajú python:3.12-slim; zvážiť slim ako predvolený po
       skúške na projektoch s natívnymi závislosťami.
Ďalej: SPEC §14, krok 3 — profil Python, parsovanie chýb, cyklus Programátor ↔ kontrola.
```

## Opravy po code review

1. Kontajner beží pod používateľom hostiteľa (nie `nobody`), inak by na Linuxe nešlo zapisovať do `/work`; root je zakázaný.
2. Ak kontajner skončí práve pri časovom limite, `kill()` vráti 409; výsledok sa už nestratí.
3. Časový limit sa rozpozná podľa `ReadTimeoutError`; stratené spojenie s Dockerom je `SandboxError`, nie časový limit.
4. Zostavenie obrazu beží cez prúd a zastaví sa pri `prepare_timeout_s`; chyby spojenia sú `SandboxError`.
5. Symbolické odkazy sa kopírujú ako odkazy (nič mimo projektu, žiadne nekonečné cykly).
6. Výstup sa číta prúdom s ohraničeným bufferom; démon drží najviac ~2× limit (`log_config`).
7. Hash obrazu zahŕňa vygenerovaný Dockerfile.
8. Vygenerovaný Dockerfile je v `.patchloop/Dockerfile`, cesty manifestov sa kontrolujú, `COPY` v JSON tvare.
9. Pracovná kópia sa maže (`remove_workspace`, kontextový manažér `workspace`).
10. `user` a `image_repository` sú v konfigurácii; neodstránený kontajner je chyba s príkazom `docker rm -f`. `WORKDIR /work` zostáva konštanta: je to dohoda medzi `image.py` a `runner.py`, nie limit.

## Druhé code review (rozhodnutie 23)

Porovnanie s OWASP Docker Security Cheat Sheet a dokumentáciou docker-py. Opravené: obídenie kontroly
roota (`sandbox.user: "00"`), koreň len na čítanie + tmpfs `/tmp`, `init`, ulimity `nofile`/`fsize`/`core`,
`USER`/`LOGNAME`, limit pamäte pri zostavení, značky na kontajneroch a obrazoch, `.env` mimo kópie,
prísnejší `remove_workspace`, `MIN_PYTHON = 3.12`. Pravidlo o nedôveryhodnej kópii je v SPEC §12.

## Overené izolácie (testy `-m docker`)

- Sieť: pripojenie na `1.1.1.1:80` zlyhá (`Network is unreachable`).
- Používateľ: proces nebeží ako root, zapisuje do `/work`; originál projektu sa nemení; pracovná kópia sa po behu dá zmazať.
- Časový limit: nekonečný cyklus je zabitý po `run_timeout_s`.
- Pamäť: pri limite 64 MB je pokus o 400 MB zabitý (OOM).
- Koreňový systém je len na čítanie, do `/tmp` sa dá zapisovať, `getpass.getuser()` funguje.
- Súbor väčší ako `max_file_mb` sa nedá zapísať (`File too large`).
- Zostavenie, ktoré prekročí `build_memory_mb`, zlyhá so `SandboxError`.
- Obraz má značku `patchloop=env`.
- Po behu kontajner zaniká (nič so značkou `patchloop` nezostáva v `docker ps -a`).
