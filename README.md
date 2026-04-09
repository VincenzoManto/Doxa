Doxa è un sistema composto da un motore Python (DoxaEngineV26) e un server API che espone le funzionalità del motore tramite HTTP e WebSocket. La struttura principale è la seguente:

- Il backend, scritto in Python, utilizza FastAPI per fornire un'API REST e due endpoint WebSocket:
  1. `/ws/agents`: per azioni in tempo reale degli agenti, chat e gestione dei portafogli personali.
  2. `/ws/resources`: per aggiornamenti in tempo reale sulle risorse.

- Il cuore del sistema è il motore (DoxaEngineV26), che gestisce agenti (DoxaAgent) configurabili tramite YAML e dotati di una "persona", regole, capacità di ragionamento (RAG), e possibilità di essere leader di sottogruppi di agenti.

- Il motore implementa logging avanzato su console, gestione di memoria vettoriale (ChromaDB), e supporta l'integrazione con modelli di AI (ad esempio, tramite autogen, vertexai, google-genai).

- Il sistema è pensato per simulazioni multi-agente, dove ogni agente può interagire, comunicare, prendere decisioni e agire in un ambiente condiviso, seguendo regole globali e locali.

- La comunicazione tra frontend e backend avviene tramite API REST e WebSocket, permettendo sia richieste sincrone che aggiornamenti in tempo reale.

Doxa è una piattaforma Python per simulazioni multi-agente, con API web e supporto per AI generativa, progettata per essere estendibile e integrabile in contesti di simulazione, ricerca o sviluppo di agenti autonomi.

### Architettura Doxa

**1. Scenario YAML**
- È il punto di partenza: definisce lo scenario simulato, gli attori (social_groups), le loro caratteristiche, relazioni e parametri contestuali.
- Ogni attore ha una “persona”, un’influenza, un canale di comunicazione e bias emotivi.
- Le relazioni tra attori (fiducia, alleanze, ostilità) sono esplicitate.

**2. Engine**
- Carica il file YAML e crea una rappresentazione interna dello scenario.
- Per ogni attore definito, istanzia un agente software con le proprietà e i comportamenti specificati.
- Gestisce lo stato globale della simulazione: portafogli, memoria, scambi, regole.
- Fornisce strumenti standard (messaggistica, scambi, pensiero, memoria, task) e strumenti custom definiti nello YAML.

**3. Agenti**
- Ogni agente rappresenta un attore sociale o organizzativo dello scenario.
- Gli agenti possono comunicare, negoziare, pensare, apprendere e agire secondo regole e vincoli.
- Possono essere organizzati gerarchicamente (leader/sub-agenti).

**4. Memoria e RAG**
- Ogni agente può avere una memoria vettoriale persistente per accumulare conoscenza durante la simulazione.
- Questa memoria può essere interrogata e aggiornata dagli agenti stessi.

**5. API e Interfacce**
- Il sistema espone API REST e WebSocket per interazione in tempo reale, controllo e monitoraggio.
- Permette l’integrazione con frontend, dashboard o altri sistemi.

---

Doxa è una piattaforma di simulazione multi-agente guidata da scenario YAML, dove ogni attore è modellato come agente autonomo dotato di strumenti, memoria e regole. L’engine orchestra la simulazione, mentre le API permettono il controllo e la visualizzazione esterna.



### ENGINE (engine.py)

- **DoxaAgent**: ogni agente è un oggetto che eredita da ConversableAgent e viene configurato tramite un dizionario (`config`) che deriva dal file YAML di scenario.
  - Attributi chiave: `persona` (descrizione comportamentale), `is_leader` (se può comandare sub-agenti), `can_rag` (abilita memoria vettoriale/RAG), `constraints` (regole globali e locali).
  - Supporta diversi provider di LLM (Ollama, OpenAI, Google, Grok) configurabili via YAML.
  - Registra strumenti standard: messaggistica privata/pubblica, proposte di scambio, accettazione/rifiuto scambi, pensiero interno, salvataggio e interrogazione della memoria RAG, assegnazione task (solo leader).
  - Registra anche operazioni custom definite nel file YAML (sezione `operations`).

- **SimulationEnvironment**: gestisce l’ambiente simulato.
  - Carica la configurazione globale e degli agenti.
  - Tiene traccia di portafogli, agenti, scambi pendenti, memoria RAG per ogni agente.
  - Metodo `reset`: crea agenti e portafogli a partire dalla configurazione YAML, supporta repliche di agenti, inizializza la memoria vettoriale per il RAG.

- **Memoria RAG**: ogni agente può avere una memoria vettoriale persistente (ChromaDB) per salvare e recuperare conoscenza testuale.

- **Interazione**: gli agenti possono comunicare, negoziare, pensare, salvare/condividere conoscenza, e (se leader) assegnare task ai sub-agenti. Tutte le azioni sono strumenti registrati e invocabili solo tramite tool, non con testo libero.

---

### FILE YAML DI SCENARIO (hormuz.yaml)

- **scenario_name/scenario_description**: nome e descrizione testuale dello scenario geopolitico simulato.

- **social_groups**: elenco dei gruppi sociali/attori simulati, ognuno con:
  - `id`: identificativo univoco.
  - `persona`: descrizione comportamentale e strategica.
  - `influence`: peso/influenza nello scenario.
  - `platform`: canale di comunicazione principale.
  - `emotional_bias`: bias emotivo dominante.

- **relationships**: relazioni tra gruppi, con livello di fiducia e descrizione qualitativa.

- **tags/extra**: metadati per categorizzare e localizzare lo scenario.
