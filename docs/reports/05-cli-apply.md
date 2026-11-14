# Správa 05 — CLI naživo, záznam behu, apply

```
ZVIT 2026-11-14 — krok 5 (CLI naživo, diff, záznam behu na disku, apply)
Hotovo: `patchloop fix` (priebeh agentov naživo, diff, vysvetlenie, vygenerovaný test označený ako nie súčasť opravy, záznam behu), `patchloop apply <run_id>` (vetva `patchloop/<run_id>`, bez commitu, pushu a `git add`), `RunResult.generated_test` (SCHEMA_VERSION 2), `runs_dir` a `git_timeout_s` v konfigurácii, `on_step` v grafe (`graph.stream`), opravy po dvoch review.
Čísla: `uv run pytest -q`: 356 jednotkových testov prešlo, `uv run ruff check .` čistý; `uv run pytest -m docker tests/docker -q`: 12 prešlo (15,1 s). Ručný beh s reálnym modelom `qwen3.5:9b-q4_K_M` na jednom vlastnom projekte (chyba v percentuálnej zľave, mimo repozitára, jeden beh, nie štatistika): `fix` skončil `fixed`/`normal`, 2 pokusy, 77 s; `apply` vytvoril vetvu bez commitu a bez staged zmien, druhé spustenie odmietnuté pre nečistý strom. Nemerané: `uv run pytest -m "docker and llm"`, beh na projekte Django alebo FastAPI.
Odchýlky od SPEC: žiadne. SPEC §5 a §10 doplnené o fakty z rozhodnutí 29 a 30 (pole `generated_test`, cesta záznamu, kódy skončenia `fix`).
Potrebné rozhodnutie: (a) nový prázdny súbor (napr. `__init__.py`) sa z diffu stráca, lebo ho obyčajný unifikovaný diff nevyjadrí; `apply` ho teda nevytvorí, hoci overená kópia ho mala. Odporúčanie: `make_diff` vydá pre prázdny nový súbor blok `diff --git` + `new file mode 100644` a `diff_paths` povolí presne tento tvar (nič iné z rozšírení gitu). Alternatíva: Programátorovi to zakázať v prompte (nespoľahlivé). (b) Pri ručnom behu model vrátil súbor bez posledného nového riadka, takže diff obsahuje `\ No newline at end of file`. Odporúčanie: kód pri aplikácii patchu zachová koncový nový riadok pôvodného súboru (o tom nemá rozhodovať model). Prompt som neladil. (c) `on_step` pohlcuje výnimky z callbacku, aby pád výpisu nezahodil beh; alternatíva je nechať ich prejsť a prísť o výsledok. Odporúčanie: ponechať.
Review: `branch-reviewer` dvakrát. Prvý: jedno Important (`_fail` cez značky Rich) a päť menších; všetko potvrdené sa opravilo s testom, ktorý najprv zlyhal. Druhý: jedno Important (riadok Testera pri základnom režime tvrdil, že testy prešli, aj keď test nevznikol) a dve menšie (`check` cez značky Rich, zlyhanie odrolovania v `apply`); opravené, tretie review nebolo. Nepotvrdené a neriešené: `runs_dir` vo vnútri projektu s inou veľkosťou písmen na macOS.
Ďalej: SPEC §14, krok 6 — Recenzent a linter (miesto v grafe je označené v `decide`).
```

## Čo sa urobilo

- **Kontrakt a konfigurácia:** `GeneratedTest(path, content, output)`, `RunResult.generated_test`, `runs_dir` (predvolene `~/.patchloop/runs`), `git_timeout_s`.
- **Záznam behu** (`runs.py`): `<runs_dir>/<run_id>/record.json`, atómický zápis, `run_id` `YYYYMMDD-HHMMSS-xxxx` overený pred použitím ako cesta, záznam inej verzie schémy alebo s nesúhlasným `run_id` sa odmietne.
- **`patchloop fix`:** kontrola prostredia pred behom, riadky priebehu z `graph.stream`, kódy skončenia 0/1/2 (rozhodnutie 30), záznam sa ukladá aj pre `no_bugs_found` a `not_fixed`; `runs_dir` vo vnútri projektu sa odmietne.
- **`patchloop apply`:** prísny parser diffu (len `---`, `+++`, `@@` a telá hunkov; žiadne premenovania, režimy ani binárne patche; cesty vnútri projektu), potom `git apply --check`, `git switch -c`, `git apply`; pri zlyhaní po vytvorení vetvy sa vráti pôvodná vetva a nová sa zmaže. Pridáva len opravu.
- **Po review:** chybové texty sa vypisujú ako text (nie značky Rich), `make_diff` a parser delia riadky len podľa `\n` (form feed), `.git` bez ohľadu na veľkosť písmen.

Podrobnosti a dôvody: rozhodnutia 29 a 30 v `docs/DECISIONS.md`.

## Známe obmedzenia

- Chýbajúci prázdny nový súbor a koncový nový riadok: viď «Potrebné rozhodnutie» (a), (b).
- `patchloop runs` a `patchloop report` ostávajú na krok 7; záznam behu je do tej doby súbor na disku.
- Beh s reálnym modelom je jeden na jednom projekte; stabilitu nedokazuje.
- `apply` pre projekt v podadresári väčšieho repozitára je pokrytý testom, ale nie ručným behom.

## Poznámky agenta

- `_fail` prvýkrát vypisoval správu cez značky Rich (pád na `[/INST]` s kódom 1): zachytilo prvé review, opravené textom a testom.
- Riadok Testera som najprv opravil len pre jeden z dvoch koncov základného režimu: zachytilo druhé review, riadok teraz preberá vetu z vysvetlenia výsledku.
- Review označilo `splitlines` ako nepotvrdené; overil som to ručne (form feed aj chýbajúci prázdny súbor v diffe) a až potom opravil.
