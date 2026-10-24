# Žurnál rozhodnutí

Každý záznam: dátum, rozhodnutie, prečo, čo sa zmenilo. Rozhodnutia robí autor projektu; návrhy Claude Code sú označené «odporúčanie» a platia až po potvrdení.

## 13. 10. 2026 — konzultácia s vedúcim

1. **Výskumná časť nie je potrebná.**
   - *Prečo:* vedúci povedal, že hlavná je praktická časť.
   - *Zmenilo sa:* projekt je semestrálny, bez štatistického vyhodnotenia (SPEC §12).
2. **Termín:** stihnúť do 10. týždňa, prísne požiadavky nie sú; teóriu a prax možno robiť paralelne.
3. **Dáta:** vedúci úlohy neposkytne; testujeme na vlastných projektoch.

## 24. 10. 2026 — upresnenie plánu

1. **Rozsah: implementácia a overenie len pre Python; architektúra jazykovo nezávislá.** *Čaká na odsúhlasenie s vedúcim.*
   - *Prečo:* všetky projekty sú v Pythone (Django, FastAPI); len na nich sa dá systém reálne otestovať. Hĺbka namiesto plytkej podpory viacerých jazykov.
   - *Zmenilo sa:* cieľ v `PLAN.md`, SPEC §1–2. Dohoda z 13. 10. («akékoľvek chyby, nie jeden jazyk») sa upresňuje, nie ruší: jazykovo špecifická logika je v profile.
2. **Profil jazyka + `patchloop.yml`; automatická detekcia podľa markerov.**
   - *Prečo:* univerzálnosť bez rozsiahlej podpory každého jazyka; užívateľ môže prepísať defaulty.
   - *Zmenilo sa:* SPEC §6. Voliteľne sa použije `Dockerfile` projektu.
3. **Dvojfázové spúšťanie:** príprava obrazu so sieťou (cache podľa hashu manifestu), kontroly bez siete.
   - *Prečo:* pieskovisko bez siete nevie inštalovať závislosti.
4. **Všetkých sedem zdrojov kontextu zostáva v pláne; poradie implementácie podľa závislostí.**
   - *Prečo:* ide o semestrálny projekt bez povinnosti merať prínos každého zdroja; stačí ich opísať a implementovať postupne.
   - *Zmenilo sa:* SPEC §7.
5. **Zastavenie cyklu:** limit iterácií (3–5), samostatný limit Recenzenta (2), detekcia stagnácie, časový limit, rollback na najlepší pokus. Stavy výsledku `fixed` / `partially_fixed` / `not_fixed` / `no_bugs_found`. Pri `partially_fixed` sa ukáže diff najlepšieho pokusu.
   - *Zmenilo sa:* SPEC §8.
6. **Testy:** existujúce testy majú prioritu; Tester dopĺňa; test musí zlyhať pred opravou; Tester nevidí opravu. Bez testov a popisu chyby implementujeme oba režimy (B: zostavenie a linter, A: základné testy, menej spoľahlivý).
   - *Zmenilo sa:* SPEC §9.
7. **Overenie funkčnosti:** demonštračné behy na vlastných projektoch so zámerne vnesenými chybami; porovnanie troch modelov stručné, bez štatistiky.
   - *Zmenilo sa:* SPEC §12.
8. **Vstup: CLI s cestou k projektu a voliteľným popisom chyby** (`--issue`, `--issue-file`). Bez popisu beží režim hľadania chýb.
   - *Prečo:* popis chyby dáva Testerovi od čoho sa odraziť; bez neho systém aspoň zostaví, spustí linter a základné testy.
9. **Výstup: predvolene len diff; pôvodný projekt sa nemení. `patchloop apply` vytvorí vetvu git a aplikuje zmeny bez commitu a pushu.**
   - *Prečo:* autor sa priklonil k vetve git, ale pôvodne nebol istý, či je to účelné. Kombinácia dáva pohodlie vetvy bez rizika pre projekt: zásah je výslovný, na samostatnej vetve, vyžaduje čistý strom.
   - *Zmenilo sa:* SPEC §10.
10. **Jazyk textov:** kód, identifikátory, komentáre a commity po anglicky; dokumentácia v `docs/` a `PLAN.md` po slovensky.
11. **Knižnice schválené s vedúcim:** LangGraph, Pydantic, LiteLLM, Ollama, docker-py, SQLAlchemy 2, Alembic, Typer, Rich, tree-sitter.
12. **Výber modelov (qwen3.5:9b, qwen2.5-coder:14b, gemma4:12b, záloha devstral:24b)** sa overí počas implementácie: dostupnosť v Ollama a pamäťové nároky (16 GB).
13. **Prostredie: Python 3.11, správca závislostí `pip` (s `venv`).** *Nahradené rozhodnutím 17.*
    - *Prečo:* autor už používa Python 3.11 v prostredí `.venv`; netreba pridávať ďalší nástroj.
    - *Zmenilo sa:* SPEC §2, §13; v `PLAN.md` namiesto «Python 3.10+» platí 3.11.
14. **Jazyk promptov a vysvetlení systému: angličtina, jazyk vysvetlení konfigurovateľný.**
    - *Prečo:* malé lokálne modely lepšie zvládajú anglické prompty; kód a chybové správy nástrojov sú tiež po anglicky.
    - *Zmenilo sa:* SPEC §2; v `patchloop.yml` pribudne kľúč `language`.
15. **Organizácia práce podľa vzoru Sentinel:** úlohy na sedenia v `docs/prompts/NN-*.md` (po anglicky), správy po sedeniach v `docs/reports/NN-*.md` vo fixnom formáte, žurnál rozhodnutí tu. Pred zverejnením repozitára sa servisné súbory (`CLAUDE.md`, `docs/prompts/`) môžu odstrániť samostatným commitom; v histórii zostanú.
16. **Referenčný projekt:** na organizáciu práce (SPEC, žurnál rozhodnutí, správy po etapách, štruktúra CLAUDE.md) sa inšpirujeme verejným repozitárom Sentinel; jeho obmedzenia knižníc sa na nás nevzťahujú.
17. **Prostredie: Python 3.12, správca závislostí `uv` (nahrádza rozhodnutie 13).**
    - *Prečo:* `uv.lock` pripína presné verzie knižníc (LangGraph, LiteLLM a ďalšie sa často menia), rovnaké prostredie na každom stroji a v Dockeri; `uv sync` je rýchly a jedným príkazom vytvorí prostredie. Rovnaký prístup má referenčný projekt. Python 3.12 podporujú všetky plánované knižnice.
    - *Zmenilo sa:* `requires-python >= 3.12`, `[dependency-groups] dev` v `pyproject.toml`, súbory `uv.lock` a `.python-version` v git, SPEC §2 a §13, `CLAUDE.md`, `README.md`. Príkazy: `uv sync`, `uv run pytest -q`, `uv run patchloop doctor`.
