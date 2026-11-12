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
24. **Inštalácia projektu: v obraze sú len závislosti, pracovná kópia sa pridáva do `PYTHONPATH` (`/work:/work/src`); základný obraz `python:3.12-slim`; stav pokusov drží graf.**
    - *Prečo:* fáza 1 kopíruje len manifesty, takže `pip install .` nemá zdrojáky. Obraz s inštaláciou projektu by sa menil s každou úpravou kódu a oprava by si vyžadovala jeho prebudovanie; s `PYTHONPATH` sa opravený súbor načíta hneď po zápise do kópie a cache obrazu platí, kým sa nezmenia manifesty. `slim` je menší a testy už bežia na ňom; chýbajúce kompilátory sa prejavia len pri balíkoch bez wheel, vrátime sa k tomu po meraní na reálnych projektoch. Stav (pokusy, najlepší pokus, počítadlá) je v stave LangGraph podľa SPEC §5, takže ho vie uložiť checkpointer.
    - *Zmenilo sa:* predvolený `sandbox.base_image` v `config.py` (`python:3.12-slim`), príklad `patchloop.yml` v SPEC §6.
25. **Stav každého pokusu = pôvodný kód + jeden zlúčený patch; ďalší pokus vychádza z najlepšieho pokusu, nie z posledného.**
    - *Prečo:* pred každým pokusom sa pracovná kópia vráti k pôvodnému kódu a aplikuje sa zlúčený patch najlepšieho doterajšieho pokusu; Programátor vidí tento kód aj jeho zostávajúce chyby a vráti celé súbory, ktoré mení; výsledný patch pokusu je zlúčenie (nové súbory prepíšu staré). Hash zlúčeného patchu tak jednoznačne popisuje stav kódu, takže detekcia stagnácie (rovnaký hash) je spoľahlivá. Rollback znamená len to, že horší pokus sa nestane základom ďalšieho. Diff pre používateľa je pôvodný kód proti zlúčenému patchu najlepšieho pokusu. Alternatíva (hromadenie bez návratu k pôvodnému stavu) by znemožnila jednoznačný hash a komplikovala rollback.
    - *Skóre pokusu:* trojica (zostavenie zlyhalo, počet všetkých chýb, počet padajúcich testov); menšia je lepšia, pri rovnosti vyhráva skorší pokus. Zlyhanie zostavenia je vždy horšie ako zlyhanie testov, lebo ďalšie kroky sa vtedy nespustia.
    - *Stagnácia:* rovnaký hash ako ktorýkoľvek skorší pokus, alebo rovnaká množina chýb ako v bezprostredne predchádzajúcom pokuse.
    - *Zmenilo sa:* nový `graph.py`, `patching.restore_files`; závislosť `langgraph` (už v zozname SPEC §13) pridaná do `pyproject.toml`.
26. **Smoke test s reálnym modelom: značka `llm` navyše k `docker`, preskočí sa pri chýbajúcom Ollama alebo modeli; výsledok sa nahlási, nevynucuje sa úspech.**
    - *Prečo:* test potrebuje bežiaci Ollama so stiahnutým modelom, čo nie je splnené všade; CLAUDE.md zakazuje reálny LLM v obyčajných testoch. Test overuje len to, že beh skončí platným stavom a pôvodný projekt ostane nedotknutý; úspešnosť opravy sa zapisuje do správy ako nameraná hodnota, aby sa prompt neladil na jeden príklad. Dostupnosť Ollama sa zisťuje cez `urllib` zo štandardnej knižnice (bez novej závislosti).
    - *Zmenilo sa:* nový `tests/test_smoke_llm.py`, značka `llm` v `pyproject.toml`.
27. **Tester: cestu súboru volí kód, vygenerovaný test sa spúšťa samostatne a nikdy nie je súčasťou opravy.**
    - *Prečo:* model vracia len obsah (`TestPlan`); cestu (`tests/test_patchloop_generated.py`, pri kolízii s číslom) určuje profil, takže model nemôže prepísať existujúci súbor. Test sa počas zostavenia a lintu v kópii nenachádza (chyby lintu v ňom by Programátor opravoval namiesto kódu) a spúšťa sa až po kontrolách projektu samostatným príkazom `test + cesta`; jeho zlyhanie je ďalší `CheckResult(stage="tests")`, takže skóre, stagnácia a rollback fungujú bez zmeny. Programátor test číta (súbor sa zapíše do kópie pred jeho promptom), ale patch, ktorý ho mení, sa odmietne. Test žije v stave grafu (`repro_test`), nie v projekte, a nie je v diffe.
    - *Kedy sa Tester volá:* pôvodné kontroly prechádzajú a (a) je popis chyby → režim `issue`, test musí zlyhať; (b) popis nie je a projekt nemá žiadny testovací súbor → režim `basic` (režim A). Ak kontroly zlyhávajú, Tester sa nevolá: zlyhania existujúcich testov sú zdroj pravdy (SPEC §9, priorita 1). Režim B je zostavenie a linter, ktoré už bežia v `check_original`.
    - *Verdikt (`classify_test_run`, profil):* `reproduces` = každé zlyhanie je neúspešné tvrdenie (`assert`, `pytest.fail`) alebo výnimka vyhodená v kóde projektu (to je samotná chyba); `broken` = všetko ostatné: chyba zberu (import, syntax), chýbajúce meno, atribút alebo fixture, zlé volanie či výnimka vo fixture v samotnom teste, časový limit, nerozpoznaný výstup a súbor, v ktorom sa nezozbieral žiadny test (pytest končí kódom 5; pri behu jedného súboru je to zlyhanie, nie úspech). Chyba testu, nie kódu, Programátorovi nejde; `passes` = prešiel. Výnimka z cudzej knižnice (nie z kódu projektu) sa zatiaľ berie ako `broken`: parser pozná len cesty vnútri kópie. Konzervatívne, a lepšie ako opačne. V režime `issue` sa `passes` a `broken` vracajú Testerovi s dôvodom; v režime `basic` je `passes` výsledok `no_bugs_found` so `reliability="reduced"`. Pokusy: `max_test_attempts` (1–3, predvolene 3); po vyčerpaní beh pokračuje bez testu (`issue`) alebo skončí `no_bugs_found` (`basic`), vždy `reduced`.
    - *Spoľahlivosť:* `normal` len ak existuje test, ktorý na pôvodnom kóde zlyháva (režim `issue`) alebo zlyhávajú existujúce testy bez popisu. S popisom a zlyhávajúcimi existujúcimi testami zostáva `reduced`, lebo kód nevie posúdiť, či tie testy súvisia s popisom.
    - *Odchýlky od SPEC §9 (schválené 2026-11-12):* režim B nemá samostatnú kontrolu importov, len `compileall` a `ruff` (import modulov bez znalosti vstupných bodov by bol heuristika); vygenerovaný test sa neukladá do `RunResult` (v kroku 5 treba rozhodnúť, či ho `patchloop apply` pridá do projektu).
    - *Zmenilo sa:* nový `agents/tester.py`, `TestPlan` v `schemas.py`, uzol `tester` v `graph.py`, `run_test_file` v `checks.py`, `test_framework`, `generated_test_path`, `test_file_command`, `classify_test_run` v profile, `has_tests` v `context/files.py`, `Config.max_test_attempts`, `propose_patch(protected=...)`.
    - *Po review (2026-11-12):*
        - Test sa vždy spúšťa obyčajným `pytest -x -q -p no:cacheprovider <súbor>`, nie pripojením cesty k `test` z konfigurácie (príkaz typu `make test` či `pytest tests/unit` by sa neobmedzil na jeden súbor). Vlastné príznaky pytestu patria do `env`.
        - Programátor vidí vygenerovaný test ako `read-only`. Nezmenená kópia testu v jeho odpovedi sa z patchu vyhodí (model ju často vráti popri oprave); zmenený test sa odmietne. Dôvod odmietnutia ide do histórie ďalšieho promptu (`HistoryEntry.refused`), inak by pri `temperature=0` prišla tá istá odpoveď znova.
        - Rovnako sa Testerovi vráti dôvod, prečo bola jeho odpoveď nepoužiteľná (`PreviousTry` bez textu testu).
        - `free_path` je obmedzená na 10 variantov a vráti `None` (adresár `tests` je odkaz alebo je plný); `apply_patch` mení chybu `mkdir` na `PatchError`. Tester v oboch prípadoch skončí bez testu (`reduced`), nikdy nezacyklí ani nespadne.
        - Vygenerovaný test sa z kópie maže cez `restore_files` (nenasleduje odkazy, rozhodnutie 23), nie cez `unlink`.
        - `has_tests`: testovým modulom je `test_*.py`, `*_test.py`, `*_tests.py` a `tests.py` (Django); pomocné súbory v `tests/` a `conftest.py` nie. Pozor: pytest bez `python_files` `tests.py` nezbiera, takže beh projektu Django s týmto súborom ostáva `no_bugs_found` ako predtým.
        - `no_bugs_found` má vysvetlenie (testy projektu prešli / základné testy prešli / nepodarilo sa vygenerovať použiteľný test).
        - *Nájdené pri ručnom behu s reálnym modelom:* pytest bez terminálu predpokladá 80 stĺpcov a dlhý riadok súhrnu skráti na `...`; správny test s `assert` dostal správu `...` a verdikt `broken`. Oprava na dvoch miestach: v kontajneri `COLUMNS=1000` (`BASE_ENV`) a parser pri správe končiacej `...` berie prvý riadok `E` z výpisu. Chyba zasahovala aj Programátora (dostával `...` namiesto dôvodu pádu).
        - *Rozhodnuté (2026-11-12):* projekt bez testov a bez popisu, ktorého zostavenie alebo linter zlyhá, dostane po oprave `reliability="normal"`. Zlyhanie zostavenia či lintu je objektívne kritérium: pôvodný kód ho nespĺňa a oprava áno. `reduced` ostáva len pre režim A (SPEC §9) a pre beh bez testu, ktorý reprodukuje chybu z popisu.

## 12. 11. 2026 — spôsob práce s agentom

28. **Pracovný postup s Claude Code je v repozitári (`.claude/`): skilly, nezávislý recenzent a pravidlá vynútené nástrojom, nie len text v `CLAUDE.md`.** *Zadané autorom («zaviesť postup z projektu helpdesk-ai-drafts a aktuálne odporúčania»); návrh potvrdený 12. 11. 2026 s dvoma úpravami: agent commituje lokálne a smie čítať `.env`.*
    - *Prečo:* doteraz bol postup opísaný v `CLAUDE.md` a v promptoch sedení; pravidlo v texte agent dodrží takmer vždy, ale nie zaručene. Dokumentácia Claude Code (Best practices) odporúča deliť pokyny na dve skupiny: čo má agent zvážiť (`CLAUDE.md`, skilly) a čo nemá výnimky (deny pravidlá, hooky). Z projektu `helpdesk-ai-drafts` sa preberá to, čo sa tam osvedčilo: cyklus «špecifikácia → zlyhávajúci test → kód → kontroly → nezávislé review → správa», kontrolný zoznam invariantov a recenzent s čistým kontextom, ktorý nemôže nič meniť.
    - *Čo sa zavádza:*
        - skill `spec-step`: cyklus jedného kroku SPEC §14. Rozhodnutia a prompt sedenia (`docs/prompts/NN-*.md`, s testami ku každému podkroku) pred kódom, test pred kódom, review, lokálne commity, správa;
        - skill `invariants-check`: invarianty P1–P12 (pieskovisko, nedotknutý originál, nedôveryhodná kópia, riadenie toku mimo modelu, ohraničené cykly, ochrany Testera, čestný výsledok, tajomstvá) so zdrojom v SPEC a s príznakmi porušenia;
        - skill `report`: formát ZVIT, len zmerané čísla;
        - subagent `branch-reviewer`: bez nástrojov na úpravu súborov; hook `reviewer_readonly.py` mu v Bash povolí len čítacie príkazy git, `ruff check` a `pytest`. Názov sa zámerne líši od agenta Recenzent v produkte;
        - `.claude/settings.json`: `git push`, `git commit --amend` a `git reset --hard` sú zakázané; merge, rebase a `uv add` vyžadujú potvrdenie;
        - commity: agent commituje lokálne (niekoľko väčších commitov na krok, Conventional Commits, súbory pridáva menovite), push, pull request a merge robí autor. Doteraz commitoval len autor; lokálny commit sa dá vrátiť, push nie, preto hranica leží tam;
        - `.env`: agent ho smie čítať, keď to práca vyžaduje; hodnoty tajomstiev nevypisuje do chatu, logov, správ ani commitov a súbor nikdy nepridáva do gitu;
        - Stop hook `checks_before_stop.py`: ak sa zmenil kód, spustí `ruff check` a jednotkové testy a červený výsledok raz vráti agentovi (pri druhom zastavení ťah skončí, aby sa dal nahlásiť stav, ktorý čaká na rozhodnutie).
    - *Čo sa nepreberá z helpdesk-ai-drafts:* riadok `Co-Authored-By` v commitoch; dokumentácia ostáva po slovensky; zákaz komentárov v kóde sa nezavádza.
    - *Čo sa nemení:* SPEC, poradie krokov v §14, formát správy, pravidlo «len súbory, ktoré žiada prompt alebo SPEC».
    - *Zmenilo sa:* nový adresár `.claude/` (`settings.json`, `agents/`, `skills/`, `hooks/`), `tests/unit/test_claude_hooks.py`, `CLAUDE.md` (časti «How we work», «Commands», «Enforced by the harness»), `.gitignore`.
