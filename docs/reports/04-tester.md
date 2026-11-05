# Správa 04 — Tester a ochrany

```
ZVIT 2026-11-05 — krok 4 (Tester a ochrany, režimy A a B)
Hotovo: agent Tester, ochrany (test musí zlyhať pred opravou, chyba testu ≠ chyba kódu, samostatný súbor, limit pokusov, Tester nevidí opravu), uzol tester v grafe, režimy A a B.
Čísla: 201 jednotkových testov prešlo, ruff čistý; docker test (2 testy) prešiel, 9,7 s. S reálnym modelom nespustené (Ollama nebežal).
Odchýlky od SPEC: režim B bez samostatnej kontroly importov; vygenerovaný test nie je v RunResult.
Potrebné rozhodnutie: (a) schváliť rozhodnutie 27 v DECISIONS.md; (b) či patchloop apply (krok 5) pridá vygenerovaný test do projektu; (c) kvalita Testera na reálnom modeli je neoverená — treba pripraviť 2–3 demo chyby (nové súbory v repozitári, najprv návrh).
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

- Skutočný model nebol na Testeri skúšaný; či `qwen3.5:9b` píše testy, ktoré zlyhajú správnym spôsobom, nie je známe.
- Súbory väčšie ako `max_file_chars` vidí model len ako úryvky (rovnako ako pri Programátorovi).
- Test importujúci kód, ktorý Programátor nevidí (nie je medzi lokálnymi importmi), nemusí viesť k oprave.
