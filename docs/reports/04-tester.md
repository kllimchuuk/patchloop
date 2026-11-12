# Správa 04 — Tester a ochrany

```
ZVIT 2026-11-05 — krok 4 (Tester a ochrany, režimy A a B)
Hotovo: agent Tester, ochrany (test musí zlyhať pred opravou, chyba testu ≠ chyba kódu, samostatný súbor, limit pokusov, Tester nevidí opravu), uzol tester v grafe, režimy A a B; opravy po review (prísnejší verdikt, súbor bez testu, read-only test, dôvody odmietnutia v promptoch, ohraničený `free_path`, bezpečné mazanie testu, `has_tests` pre Django).
Čísla: 228 jednotkových testov prešlo, ruff čistý; 12 docker testov prešlo (`pytest -m docker tests/docker`, 20,6 s). Ručný beh s reálnym modelom `qwen3.5:9b-q4_K_M` na troch vlastných chybách (po jednom behu, mimo repozitára): A (padá existujúci test) `fixed`/`normal`, 28 s; B (len popis chyby) `fixed`/`normal`, Tester 15 s + Programátor 11 s; C (bez testov a bez popisu) `fixed`/`reduced`, Tester 34 s + Programátor 15 s.
Odchýlky od SPEC: režim B bez samostatnej kontroly importov; vygenerovaný test nie je v RunResult.
Potrebné rozhodnutie: (a) schválené 2026-11-12: rozhodnutie 27 v DECISIONS.md (vrátane odseku „Po review“); (a2) vyriešené: `reliability` ostáva `normal` pre projekt bez testov so zlyhaním zostavenia/lintu (zapísané v rozhodnutí 27); (b) vygenerovaný test: `apply` ho podľa odporúčania nepridáva, ale `RunResult` by ho mal niesť, aby ho CLI ukázalo (zmena kontraktu, krok 5); (c) Tester je overený na troch chybách (jeden beh každej, nie štatistika); demo chyby zatiaľ ležia mimo repozitára a ich pridanie do repozitára treba najprv schváliť; (d) Programátor v behu B vrátil navyše súbor `explanation` (text vysvetlenia ako súbor) a dostal sa do diffu; návrh: pravidlo do promptu, že `files` sú len cesty projektu, a odmietnutie takého patchu; prompt som neladil.
Ďalej: SPEC §14, krok 5 — CLI naživo, diff, apply.
```

## Čo sa urobilo

- **Kontrakt:** `TestPlan(content, explanation)`; cestu súboru volí kód, nie model.
- **Agent** (`agents/tester.py`): prompt v angličtine, kontext = zdrojové súbory pôvodného kódu (opravu nevidí, lebo beží pred prvým pokusom), pri odmietnutom teste sa vráti predchádzajúci test s dôvodom.
- **Ochrany:** profil klasifikuje beh testu na `reproduces` / `passes` / `broken`; `broken` (import, syntax, názov, časový limit, nerozpoznaný výstup) sa Programátorovi nikdy nedostane. Limit `max_test_attempts` 1–3.
- **Graf:** `check_original` → `tester` (ak pôvodné kontroly prechádzajú a je popis chyby alebo projekt nemá testy). Vygenerovaný test sa spúšťa samostatne po kontrolách projektu, Programátor ho vidí, ale nesmie ho meniť, v diffe nie je.
- **Režimy:** B = zostavenie a linter (už existovali); A = základné testy pre projekt bez testov a bez popisu, výsledok vždy `reliability="reduced"`.

Podrobnosti a dôvody: rozhodnutie 27 v `docs/DECISIONS.md`.

## Známe obmedzenia

- Tester na `qwen3.5:9b` napísal v behoch B a C test, ktorý zlyhal správnym spôsobom (`assert`), ale ide o jeden beh na každú z troch chýb; stabilitu to nedokazuje. Prvý beh B skončil časovým limitom Ollama (120 s) pri volaní Programátora a pri opakovaní prešiel; limit `llm.timeout_s` je teda pri studenom modeli tesný.
- Súbory väčšie ako `max_file_chars` vidí model len ako úryvky (rovnako ako pri Programátorovi).
- Test importujúci kód, ktorý Programátor nevidí (nie je medzi lokálnymi importmi), nemusí viesť k oprave.
