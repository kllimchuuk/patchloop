# Sedenie 03: správa o práci

**Etapa:** profil Python, parsovanie chýb, cyklus Programátor ↔ kontrola (SPEC §14, krok 3)
**Úloha:** `docs/prompts/03-python-profile.md`
**Dátum:** 2. 11. 2026 · **Vykonávateľ:** Claude Code (Sonnet 5.5)

```
ZVIT 2. 11. 2026 — Sedenie 03, profil Python a cyklus opráv
Hotovo: profil Python (detekcia Django/FastAPI, manifesty, predvolené príkazy), parsery výstupu
        compileall/ruff/pytest, spúšťač kontrol, aplikácia a validácia patchov, zber kontextu,
        agent Programátor, graf LangGraph s limitmi a stavmi výsledku (rozhodnutia 24 a 25),
        voliteľný smoke test s reálnym Dockerom a reálnym modelom.
Čísla: 159 testov bežne (0,39 s), ruff bez chýb; 11 testov s -m docker (7,5–11,7 s);
       smoke test (docker + llm, qwen3.5:9b-q4_K_M, chyba v jednom riadku, 4 behy):
       4× fixed, 4× hneď prvým pokusom (best_attempt=0), 20,8 s (prvý beh) a 9,6 / 10,1 / 9,7 s.
Odchýlky od SPEC: metóda profilu sa volá parse_check (nie parse_errors) a berie ExecResult;
       max_attempts ostáva na najvyššej úrovni konfigurácie (1–10, predvolene 4);
       pytest s kódom 5 (nič nezozbierané) sa berie ako úspech.
Potrebné rozhodnutie: (a) súbory väčšie ako loop.max_file_chars (12000) vidí model len ako
       úryvky a nemôže ich opraviť, kým nebude navigácia cez tree-sitter; (b) Poetry nie je
       podporované; (c) opakované neplatné alebo prázdne odpovede modelu sa nepočítajú ako
       stagnácia (obmedzuje ich len max_attempts).
Ďalej: SPEC §14, krok 4 — Tester (generovanie testu, ktorý na pôvodnom kóde padá).
```

## Čo sa urobilo

- **Profil Python** (`profiles/`): detekcia Django (manage.py + `DJANGO_SETTINGS_MODULE`), FastAPI (presný názov závislosti), inak všeobecný projekt; manifesty vrátane `-r` a závislostí z `pyproject.toml`; predvolené príkazy zostavenia (`compileall`), lintu (`ruff`) a testov (`pytest`).
- **Parsery** (`python_errors.py`): výstup troch nástrojov sa mení na `CheckResult`; testy bežia nad skutočne zachytenými výstupmi (`tests/fixtures/outputs/`). Časový limit a nedostatok pamäte sú `Failure(kind="runtime")`. Ak parser nič nenájde, zlyhanie dostane `raw_tail`.
- **Kontroly** (`checks.py`): zostavenie → lint → testy; zlyhané zostavenie zastaví ďalšie kroky.
- **Patche** (`patching.py`, `Patch` v `schemas.py`): cesty od modelu sú nedôveryhodné (absolútne, `..`, `.git`, spätné lomky, NUL sa odmietnu), nenasledujú sa symbolické odkazy; diff kompatibilný s `git apply`; `restore_files` vracia súbory k pôvodnému stavu.
- **Kontext a Programátor** (`context/files.py`, `agents/programmer.py`): súbory s chybami a ich lokálne importy v rozpočte znakov; Programátor vracia celé súbory; patch, ktorý prepisuje súbor nezobrazený celý, alebo nič nemení, sa odmietne. Model dvakrát neplatne odpovedal → `LLMInvalidAnswer` (stratený pokus, nie celý beh).
- **Graf** (`graph.py`): uzly prepare, check_original, fix, apply, check, decide, finish. Zastavenie: úspech, limit pokusov, stagnácia, časový limit. Stavy: `fixed`, `partially_fixed`, `not_fixed`, `no_bugs_found`. Pri zadanom popise chyby je `reliability="reduced"`, lebo ešte nie je Tester. Miesta pre Reviewera a Testera sú v kóde označené.
- **Oprava nájdená pri reálnom Dockeri:** `compileall` zapisoval `__pycache__` do kópie, takže oprava rovnakej veľkosti v tej istej sekunde ostala skrytá za starým `.pyc` (2 zo 5 behov zlyhali). Riešenie: `PYTHONPYCACHEPREFIX=/tmp/pycache`; potom 8/8 behov prešlo. Test s opravou rovnakej veľkosti je regresný.

## Smoke test

`tests/test_smoke_llm.py`, značky `docker` a `llm`, mimo bežného behu (`uv run pytest -m "docker and llm" -s`). Ak Docker, Ollama alebo model chýbajú, test sa preskočí s vysvetlením. Projekt: funkcia `add` vracia `a - b`, jeden test. Reálny Docker a reálny model `qwen3.5:9b-q4_K_M` (thinking vypnutý).

| Beh | Stav | Pokusy | Čas |
|---|---|---|---|
| 1 | fixed | 1 | 20,8 s |
| 2 | fixed | 1 | 9,6 s |
| 3 | fixed | 1 | 10,1 s |
| 4 | fixed | 1 | 9,7 s |

Prvý beh je pomalší (pravdepodobne načítanie modelu do pamäte; neoverené). Je to jedna triviálna chyba, takže to nič nehovorí o kvalite na reálnych projektoch. Prompt sa pre tento príklad neladil.

## Známe obmedzenia

- Reálny model bol zatiaľ spustený len na tomto jednom príklade; kvalita promptu na väčších projektoch nie je známa.
- Django a FastAPI sú otestované len cez pytest; formát výstupu pytestu je zachytený z lokálnej verzie.
- Chyba, ktorá sa nedá dosiahnuť zo súborov s chybami a ich lokálnych importov, je pre Programátora neviditeľná.
- Základný obraz `slim` nemá kompilátory; balíky bez wheel sa môžu nenainštalovať (rozhodnutie 24).
