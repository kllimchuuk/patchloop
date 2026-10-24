# Sedenie 01: správa o práci

**Etapa:** kostra projektu, konfigurácia, kontrakty, klient LLM so štruktúrovanou odpoveďou, `patchloop check`
**Úloha:** `docs/prompts/01-skeleton.md`
**Dátum:** 24. 10. 2026 · **Vykonávateľ:** Claude Code (Sonnet 5.5)

```
ZVIT 24. 10. 2026 — Sedenie 01, kostra
Hotovo: balík patchloop (src-layout, uv, Python 3.12), config.py, schemas.py (SCHEMA_VERSION = 1),
        llm/client.py + cache.py + FakeLLMClient, príkaz patchloop check, 24 testov,
        prvá skutočná požiadavka na model je vykonaná (jednorazový skript potom odstránený).
Čísla: 24 testov (0,1 s), ruff bez chýb; prvá požiadavka na qwen3.5:9b-q4_K_M: 17,7 s (vrátane
       načítania modelu), potom 11,3–11,4 s pre úlohu s jednou funkciou; 100 % GPU, rušič llamacpp,
       kontext 16384, veľkosť modelu 6,1 GB.
Odchýlky od SPEC: (1) predvolené hodnoty konfigurácie sú v modeloch Pydantic, nie v
       configs/default.yaml, inak by nainštalovaný balík súbor nenašiel; (2) zadanie sedenia uvádzalo
       Python 3.11 a pip, neskôr nahradené uv a Python 3.12 (rozhodnutie 17); (3) model qwen3.5:9b
       nahradený značkou q4_K_M (rozhodnutie 18).
Potrebné rozhodnutie: (a) ponechať llm.timeout_s = 120 s; pri úlohách s viacerými súbormi bude čas
       dlhší, preto zvážiť vypnutie «thinking» modelu (parameter think) a zmerať rozdiel;
       (b) kľúč cache (model, správy, schéma) bude možno potrebovať num_ctx a temperature, keď
       pribudnú rôzne režimy.
Ďalej: SPEC §14, krok 2 — pieskovisko (príprava obrazu, spustenie bez siete, limity).
```

## Dôležité zistenie

Na Apple Silicon príkaz `ollama pull qwen3.5:9b` stiahne variant MLX (`nvfp4`), ktorý odpovedá
`structured output is unavailable` aj na najjednoduchšiu požiadavku `format: json`. Variant
`qwen3.5:9b-q4_K_M` (GGUF) so schémou JSON funguje. Záver je zapísaný v `docs/DECISIONS.md`, záznam 18.
