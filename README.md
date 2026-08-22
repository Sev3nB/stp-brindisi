# STP Brindisi personale

Applicazione Flask con database Supabase/PostgreSQL per consultare fermate e
corse programmate pubblicate da STP Brindisi nei feed GTFS ufficiali.

Funzioni principali:

- elenco completo delle linee urbane ed extraurbane;
- sezione Orari dedicata, filtrabile per giorno, servizio, linea e direzione;
- dettaglio di ogni linea con direzioni, varianti e fermate ordinate;
- mappa di tutte le fermate filtrabile per città e servizio;
- pianificatore automatico da indirizzi, luoghi, GPS, punti sulla mappa, luoghi
  salvati o fermate;
- ricerca nel grafo STP di corse dirette e itinerari fino a due cambi, con
  accesso e arrivo a piedi, attese e piccoli cambi pedonali;
- percorsi approssimati sulla rete stradale tramite OSRM/OpenStreetMap;
- orari giornalieri delle singole linee;
- modalità chiara/scura;
- linee e fermate preferite salvate nel browser;
- luoghi personali e posizione GPS sulla mappa.
- fermate più vicine utilizzabili direttamente come partenza nel pianificatore;
- pannello preferiti con azioni “Parti da qui” e “Arriva qui”.

## Come funziona il pianificatore

Gli indirizzi e i punti di interesse vengono convertiti in coordinate tramite
Photon/OpenStreetMap. Il motore trova più fermate realisticamente raggiungibili
vicino ai due estremi e svolge una ricerca temporale a turni, simile a RAPTOR,
sui viaggi GTFS attivi nel giorno scelto. A ogni turno esplora le corse che si
possono realmente prendere dopo l'arrivo alla fermata e consente anche un breve
trasferimento a piedi tra fermate vicine.

Il costo considera l'orario di arrivo, i cambi e la distanza a piedi; vengono
mostrate fino a tre alternative non duplicate. Gli orari degli autobus sono
quelli programmati nel GTFS. Durata e percorso dei tratti a piedi sono stime e
non includono traffico, ritardi o accessibilità del marciapiede.

Il motore scarta inoltre le combinazioni che usano l'autobus per una sola
fermata breve, che lasciano quasi tutto il tragitto da percorrere a piedi o che
richiedono una camminata complessiva eccessiva. Le fermate entro il raggio
preferito hanno precedenza; il raggio massimo viene usato solo quando non ce ne
sono di più vicine.

Poiché i feed STP non contengono `shapes.txt`, il tracciato stradale viene
calcolato da OSRM passando in ordine per tutte le fermate. È molto più fedele
delle linee rette, ma non costituisce un percorso ufficiale STP. Se OSRM non è
raggiungibile, l'app mostra automaticamente il collegamento tratteggiato tra le
fermate.

La geolocalizzazione del browser richiede un contesto sicuro: funziona su
`localhost` oppure quando l'app è pubblicata in HTTPS. Da telefono, un semplice
indirizzo locale `http://192.168...` potrebbe non ricevere il permesso GPS.

## Avvio rapido

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
# Inserisci in .env la connection string copiata da Supabase → Connect
python scripts/update_gtfs.py
python app.py
```

Apri `http://127.0.0.1:5000`. Per usarla dal telefono sulla stessa rete:

```bash
python app.py --host 0.0.0.0
```

Poi apri dal telefono `http://IP-DEL-PC:5000`.

## Preparazione di Supabase

1. Crea un progetto su Supabase.
2. Premi **Connect** nel dashboard.
3. Copia la **Session pooler connection string** (porta 5432), compatibile IPv4.
4. Copia `.env.example` in `.env` e sostituisci la stringa di esempio.
5. Esegui `python scripts/update_gtfs.py`.

Lo script crea automaticamente lo schema privato `gtfs`, scarica i quattro
feed ufficiali e carica i dati con PostgreSQL `COPY`. L'aggiornamento avviene
in una sola transazione: se qualcosa fallisce, i dati precedenti restano
intatti. Se i file STP non sono cambiati, termina senza riscrivere le tabelle.
Non inserire mai `.env` in Git.

## Pubblicazione su Vercel e aggiornamento GTFS

Vercel deve eseguire soltanto l'app Flask: non avviare `update_gtfs.py` durante
la build o all'interno di una funzione serverless. Nel progetto Vercel aggiungi
`DATABASE_URL` in **Settings → Environment Variables** e usa la stessa Session
pooler di Supabase.

Il repository include `.github/workflows/update-gtfs.yml`, che aggiorna il
database ogni lunedì e può essere avviato manualmente. Dopo aver pubblicato il
repository su GitHub:

1. apri **GitHub → repository → Settings → Secrets and variables → Actions**;
2. crea un nuovo repository secret chiamato esattamente `DATABASE_URL`;
3. inserisci come valore la connection string Session pooler di Supabase;
4. apri la scheda **Actions → Aggiorna dati STP**;
5. premi **Run workflow** per effettuare subito il primo caricamento.

La variabile va quindi configurata sia su Vercel, per leggere gli orari, sia
nei Secrets di GitHub, per aggiornarli. Non copiarla dentro il codice.

I dati sono orari programmati, non posizioni o ritardi in tempo reale. Fonte:
STP Brindisi S.p.A., open data GTFS (CC BY 4.0).

## Test

Con `DATABASE_URL` configurato, vengono eseguiti anche i test di integrazione.

```bash
python -m unittest discover -s tests -v
```
