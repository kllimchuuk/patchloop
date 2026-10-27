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
15. **Organizácia práce podľa vzoru Sentinel:** úlohy na sedenia v `docs/prompts/NN-*.md` (po anglicky), správy po sedeniach v `docs/reports/NN-*.md` (po slovensky) vo fixnom formáte, žurnál rozhodnutí tu. Pred zverejnením repozitára sa servisné súbory (`CLAUDE.md`, `docs/prompts/`) môžu odstrániť samostatným commitom; v histórii zostanú.
16. **Referenčný projekt:** na organizáciu práce (SPEC, žurnál rozhodnutí, správy po etapách, štruktúra CLAUDE.md) sa inšpirujeme verejným repozitárom Sentinel; jeho obmedzenia knižníc sa na nás nevzťahujú.
17. **Prostredie: Python 3.12, správca závislostí `uv` (nahrádza rozhodnutie 13).**
    - *Prečo:* `uv.lock` pripína presné verzie knižníc (LangGraph, LiteLLM a ďalšie sa často menia), rovnaké prostredie na každom stroji a v Dockeri; `uv sync` je rýchly a jedným príkazom vytvorí prostredie. Rovnaký prístup má referenčný projekt. Python 3.12 podporujú všetky plánované knižnice.
    - *Zmenilo sa:* `requires-python >= 3.12`, `[dependency-groups] dev` v `pyproject.toml`, súbory `uv.lock` a `.python-version` v git, SPEC §2 a §13, `CLAUDE.md`, `README.md`. Príkazy: `uv sync`, `uv run pytest -q`, `uv run patchloop check`.
18. **Model: `qwen3.5:9b-q4_K_M` (GGUF, rušič llama.cpp), nie predvolený tag `qwen3.5:9b`.**
    - *Prečo:* na Macu s Apple Silicon `ollama pull qwen3.5:9b` stiahne variant MLX (`nvfp4`, 7,6 GB), ktorý nepodporuje štruktúrovaný výstup (`structured output is unavailable`, overené priamo cez API Ollama). Variant `q4_K_M` (6,6 GB, ako v pláne) štruktúrovaný výstup podporuje a beží 100 % na GPU.
    - *Zmenilo sa:* predvolený `llm.model` v `config.py`, hint v `patchloop check`. Pri výbere ďalších modelov vždy pripájať explicitný tag kvantizácie.
19. **Kontextové okno: `llm.num_ctx = 16384` v konfigurácii.**
    - *Prečo:* Ollama predvolene používa 4096 tokenov, čo nestačí na kód súborov, chyby a históriu pokusov.
    - *Zmenilo sa:* `LlmConfig.num_ctx`, odovzdáva sa v každej požiadavke.
20. **«Thinking» modelu je predvolene vypnutý (`llm.thinking: false`).**
    - *Prečo:* orientačné meranie na dvoch malých chybách (po 3 behy, model `qwen3.5:9b-q4_K_M`, štruktúrovaná odpoveď): bez thinking 3,2 s a 12,3 s, s thinking 12,8 s a 15,1 s; správnosť rovnaká (3/3 v oboch režimoch). Cez LiteLLM: 5,3 s proti 13,6 s. Na malých úlohách thinking nepridáva kvalitu, len čas.
    - *Zmenilo sa:* `LlmConfig.thinking`, v požiadavke `reasoning_effort="none"` (zapnuté: `"low"`). Pri ťažších chybách sa môže oplatiť zapnúť thinking pre Programátora; vrátime sa k tomu pri testovaní na vlastných projektoch.
21. **Predvolené hodnoty konfigurácie sú v modeloch Pydantic (`config.py`), nie v `configs/default.yaml`.**
    - *Prečo:* `configs/` leží mimo `src/patchloop/`, takže nainštalovaný balík by súbor nenašiel. Hodnoty v modeloch sú na jednom mieste, typované a validované; `patchloop.yml` ich prepíše.
    - *Zmenilo sa:* SPEC §13 (opis `config.py` a `configs/`).
22. **Pieskovisko: obraz sa zostavuje cez Dockerfile s tagom podľa hashu, kontrola beží v jednorazovom kontajneri bez siete pod používateľom hostiteľa; testy s reálnym Dockerom sú voliteľné.**
    - *Prečo:* tag `<image_repository>:<hash>` (vygenerovaný Dockerfile a obsah manifestov) dá cache bez vlastnej evidencie: rovnaké vstupy znamenajú rovnaký obraz a zostavenie sa preskočí; zmena šablóny Dockerfile znamená nový obraz. Zostavenie (so sieťou) a spustenie (`network_mode="none"`) sú oddelené fázy podľa SPEC §6. Kontajner beží pod `uid:gid` hostiteľa (nikdy nie root; dá sa zmeniť `sandbox.user`), aby sa do pripojenej kópie projektu dalo zapisovať aj na Linuxe a aby sa dala potom zmazať; ďalej `cap_drop=ALL`, `no-new-privileges`, limity pamäte, CPU a procesov. Kópia projektu kopíruje symbolické odkazy ako odkazy, takže sa do pieskoviska nedostane nič mimo projektu. Testy bežia s falošným klientom Dockeru; testy s reálnym kontajnerom majú značku `docker` a spúšťajú sa `pytest -m docker`, pretože potrebujú démon a stiahnutý základný obraz (CLAUDE.md zakazuje sieť v obyčajných testoch).
    - *Obmedzenie:* `prepare_timeout_s` sa kontroluje pri každom riadku výstupu zostavenia; zostavenie, ktoré nič nevypisuje, zastaví časový limit čítania HTTP s rovnakou hodnotou. V najhoršom prípade teda zostavenie trvá menej ako dvojnásobok limitu.
    - *Zmenilo sa:* nový balík `sandbox/`, sekcia `sandbox` v konfigurácii, závislosť `docker` (už schválená v SPEC §13), značka `docker` v `pyproject.toml`.
23. **Spevnenie pieskoviska po druhom code review (podľa OWASP Docker Security Cheat Sheet).**
    - *Čo:* koreňový súborový systém kontajnera len na čítanie, `/tmp` ako tmpfs s limitom veľkosti (`nosuid,nodev`); proces `init` (zbiera osirotené procesy); ulimity `nofile`, `fsize`, `core=0` (`nproc` nie: bez menného priestoru používateľov počíta všetky procesy uid hostiteľa, preto ostáva `pids_limit`); `sandbox.user` len číselne a nikdy uid 0 (reťazec `"00"` predtým prešiel ako root); `USER`/`LOGNAME` pre uid hostiteľa bez záznamu v `/etc/passwd`; limit pamäte aj pre zostavenie obrazu (`sandbox.build_memory_mb`), pretože inštalácia závislostí spúšťa ich kód so sieťou; značka `patchloop` na kontajneroch a obrazoch (`LABEL` je v Dockerfile, takže je súčasťou hashu).
    - *Pravidlo pre ďalšie kroky:* pracovná kópia je po behu nedôveryhodná. Kód v kontajneri môže vytvoriť symbolický odkaz na ľubovoľný súbor hostiteľa, preto čítanie súborov pre agentov, výpočet diffu a `patchloop apply` nenasledujú odkazy a pracujú len s cestami vnútri kópie (SPEC §12).
    - *`.env`:* do pieskoviska sa predvolene nekopíruje (môže obsahovať skutočné tajomstvá, ktoré by sa dostali do výstupu, k modelu a do záznamu behu); povoliť sa dá `sandbox.copy_env: true`. Šablóny `.env.example`, `.env.sample`, `.env.template` sa kopírujú vždy.
    - *Ostatné:* `remove_workspace` maže len adresáre vytvorené v tom istom procese (predtým stačila predpona názvu). `patchloop check` vyžaduje Python 3.12 (zosúladené s rozhodnutím 17).
    - *Známe obmedzenia (bez zmeny):* základný obraz je zadaný tagom, nie digestom (digest zapíšeme do záznamu behu v kroku 7); docker-py zostavuje cez klasický builder, nie BuildKit; stdout a stderr sa čítajú oddelene, takže sa stráca ich vzájomné poradie; zápis do `/work` obmedzuje len `fsize` na jeden súbor, nie celkový objem.
    - *Zmenilo sa:* `sandbox/runner.py`, `sandbox/image.py`, `sandbox/workspace.py`, nové kľúče `sandbox.tmp_mb`, `max_open_files`, `max_file_mb`, `build_memory_mb`, `copy_env`; SPEC §12.
