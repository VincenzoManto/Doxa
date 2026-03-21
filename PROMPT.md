L'approccio suggerito dall'altra AI (usare PydanticAI e JSON) è eccellente per modelli come **Qwen 2.5 7B** o **GPT-4**, ma con **Qwen 0.5B** rischi il fallimento totale. I modelli così piccoli "si rompono" spesso quando devono chiudere correttamente le parentesi graffe del JSON o gestire schemi annidati.

Per far funzionare il tuo progetto con **Qwen 0.5B**, dobbiamo fondere l'idea dello **stato strutturato** (Pydantic per il codice) con un **output a tag** (per l'IA).

Ecco il prompt definitivo, ottimizzato per GitHub Copilot, che integra i punti di forza di entrambi i suggerimenti e risolve il problema della RAM e del parallelismo.

***

### PROMPT PER GITHUB COPILOT

"Agisci come Senior Software Architect. Devo costruire un simulatore di Swarm Intelligence ispirato a MiroFish. 

**Vincoli Tecnici:**
- **Modello:** Ollama `qwen:0.5b` (deve gestire output via tag XML, NON JSON, perché è troppo piccolo).
- **Orchestratore:** Usa una logica ispirata a **OpenAI Swarm** (stateless e basata su funzioni) ma implementata con **Python Asyncio** per il parallelismo reale degli agenti.
- **Backend:** Flask con supporto per WebSockets (Flask-SocketIO) per aggiornamenti in tempo reale al frontend.
- **Frontend:** React.

**Logica del Mondo (YAML):**
Il sistema deve caricare un `world_config.yaml` che definisce:
- `resources`: (es. oro, cibo, energia) con vincoli globali.
- `actors`: nome, descrizione, portfolio iniziale e 'constraints' personali (es. 'non scambiare mai sotto le 10 unità di oro').
- `context`: lo scenario (es. 'Guerra commerciale tra colonie spaziali').

**Architettura dell'Agente (Loop di Pensiero):**
Ogni agente ad ogni 'tick' di simulazione riceve il contesto e il proprio portfolio. Deve produrre un output in questo formato testuale:
1. `<THOUGHT>`: Ragionamento interno (privato).
2. `<PUBLIC_MSG>`: Messaggio per la piazza globale.
3. `<PRIVATE_MSG target="NomeAgente">`: Messaggio diretto.
4. `<ACTION>`: Comandi tipo `TRADE(target, risorsa, quantità, in_cambio_di)`.

**Requisiti del Codice:**
1. **Parser Robusto:** Crea una classe `ActionParser` in Python che usa Regex per estrarre il contenuto dei tag XML dall'output di Qwen 0.5b.
2. **World Manager:** Una classe Python che valida le azioni. Se un agente prova a scambiare risorse che non ha, l'azione fallisce e viene riportato l'errore nel prompt del tick successivo (feedback loop).
3. **Parallelismo:** Usa `asyncio.gather` per far 'pensare' tutti gli agenti contemporaneamente su Ollama.
4. **User Impersonation:** Un endpoint API deve permettere all'utente di iniettare messaggi `<PUBLIC_MSG>` o azioni manuali come se fosse uno degli attori.
5. **State Sync:** Dopo ogni tick, invia lo stato aggiornato dei portfolio e i log delle chat al frontend React tramite WebSocket.

1. Una classe per file
2. Frontend in Vite con Tailwind in CDN
3. Parser YML per la configurazione
4. Ollama con qwen:0.5b in locale
5. Deve poter modellizzare scenari geopolitici, economici, sociali, commerciali
6. Gli agenti devono poter interagire tra loro tramite messaggi pubblici e privati
7. Gli agenti devono poter eseguire azioni come scambiare risorse, fare offerte, ecc.
8. Gli agenti possono unirsi in room
9. I portfolio sono soggetti a constraints definibili nella configurazione
10. Ci possono essere portfoli globali che hanno un costo di mining (sia di tempo (cicli di tick) che di risorse)
11. Il frontend deve essere figo, bello, completo e mostrare grafi, chat, log e portfolio in tempo reale (con websocket per aggiornamenti in tempo reale dal backend)

Genera il codice di base per questi file, assicurandoti che il prompt di sistema per Qwen 0.5b sia estremamente semplice e focalizzato sull'uso dei tag."

***

### Perché questo approccio è superiore per il tuo caso:

1.  **Tag XML vs JSON:** Per un modello da 0.5B, scrivere `<ACTION>VENDO</ACTION>` è naturale come scrivere testo. Scrivere `{"action": "vendo"}` richiede una precisione sintattica che spesso quel modello non ha, portando a errori di crash del sistema.
2.  **Asyncio invece di Loop Semplici:** Se hai 10 agenti, con un loop semplice aspetteresti 10 volte il tempo di risposta di Ollama. Con `asyncio`, Ollama (se hai abbastanza VRAM/Compute) gestisce le richieste in parallelo o in coda ottimizzata.
3.  **Il "Feedback Loop":** Se l'IA sbaglia (es. vuole dare 100 monete ma ne ha 10), il `WorldManager` Python intercetta l'errore e nel turno dopo gli dice: *"Errore: hai provato a dare 100 monete ma ne hai solo 10"*. Questo rende l'IA "consapevole" dei propri limiti fisici senza dover essere un modello gigante.
4.  **YAML come Database:** Usare lo YAML ti permette di cambiare scenario (da un mercato di pesci a una guerra nucleare) in 2 secondi senza toccare una riga di codice Python.

**Consiglio tecnico:** Quando configuri il prompt di sistema per Qwen, dì esplicitamente: *"Rispondi SOLO usando i tag indicati. Non aggiungere chiacchiere fuori dai tag."* Questo è vitale per i modelli piccoli.

Qui un esempio dell'utilizzo dello Swarm 

'''python
import json
from pydantic import BaseModel
from openai import OpenAI

# 1. Configurazione Client Ollama
client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)

# 2. Definizione del Portfolio e dello Stato
class Portfolio(BaseModel):
    denaro: int
    risorse: dict  # es: {"legna": 10, "ferro": 5}

class Agente:
    def __init__(self, nome, config_llm, portfolio_iniziale):
        self.nome = nome
        self.model = config_llm
        self.portfolio = portfolio_iniziale
        self.memoria_messaggi = []

    def sistema_prompt(self):
        return f"""Sei {self.nome} in una simulazione sociale.
        Il tuo portfolio attuale: {self.portfolio.json()}
        Regole: Non puoi scambiare più di quello che hai. Sii strategico."""

    def invia_proposta(self, destinatario_nome, messaggio):
        prompt = f"Messaggio da {destinatario_nome}: '{messaggio}'. Cosa rispondi e che azione fai?"
        
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.sistema_prompt()},
                {"role": "user", "content": prompt}
            ],
            # Chiediamo un output strutturato (JSON) per gestire lo scambio
            response_format={ "type": "json_object" }
        )
        return json.loads(response.choices[0].message.content)

# 3. Motore della Società (Gestore dei Vincoli)
class Societa:
    def __init__(self):
        self.agenti = {}

    def aggiungi_agente(self, agente):
        self.agenti[agente.nome] = agente

    def esegui_scambio(self, mittente_nome, destinatario_nome, risorsa, quantita):
        mittente = self.agenti[mittente_nome]
        destinatario = self.agenti[destinatario_nome]

        # CONSTRAINT: Controllo risorse
        if mittente.portfolio.risorse.get(risorsa, 0) >= quantita:
            mittente.portfolio.risorse[risorsa] -= quantita
            destinatario.portfolio.risorse[risorsa] = destinatario.portfolio.risorse.get(risorsa, 0) + quantita
            print(f"✅ SCAMBIO AVVENUTO: {mittente_nome} -> {quantita} {risorsa} -> {destinatario_nome}")
        else:
            print(f"❌ FALLIMENTO: {mittente_nome} non ha abbastanza {risorsa}")

# --- ESECUZIONE SIMULAZIONE ---

# Inizializziamo la società
mondo = Societa()
mondo.aggiungi_agente(Agente("Agente_A", "qwen2.5:7b", Portfolio(denaro=100, risorse={"legna": 20})))
mondo.aggiungi_agente(Agente("Agente_B", "qwen2.5:3b", Portfolio(denaro=50, risorse={"ferro": 10})))

# Simuliamo un'interazione
proposta = mondo.agenti["Agente_A"].invia_proposta("Agente_B", "Ti do 5 legna per 2 ferro")
print(f"Azione decisa da A: {proposta}")

# Il motore valida l'azione (Constraint logic)
if "azione" in proposta and proposta["azione"] == "scambio":
    mondo.esegui_scambio("Agente_A", "Agente_B", proposta["risorsa"], proposta["quantita"])
'''



voglio usare ollama in locale con qwen0.5b. voglio usare un orchestratore di swarm intelligence che già esiste in python (non voglio creare tutto da 0 e reinventare la ruota). ogni AI deve:
avere un portfoglio di risorse (materiali o descrittive)
poter far azioni sul suo portfolio scambiando con il sistema o con altre AI
chattare in room con altre AI (tipo chat privata, oppure chat a 3)
pubblkicare messaggi pubblici che tutte le AI possono leggere
deve poter pensare (quindi tenere messaggi privati a sè stessa)
qwen0.5b lavora bene su piccole RAM quindi non può fare pensieri giganti e non sa fare JSON in modo preciso, quindi va trovata una soluzione
ogni AI deve poter lavorare in parallelo
l'utente deve poter impersonare un attore (quindi inviare messaggi privati, pubblici, scambiare a nome di un attore).
la configurazione del mondo deve essere un YML così da essere facilmente configurabile
la configurazione può definire risorse globali, attori, contesto e constraints delle risorse. ogni portfoglio può anche avere dei constraints suoi "economici".
deve essere possibile modellare scenari geopolitici, economici ma anche industriali e commerciali
frontend in react e backend in flask python

Deve poter lavorare con scenari complessi tipo quanto riportato in @./hormuz.yaml