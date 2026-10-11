# Avviso disponibilità XS H&M

Controlla la taglia **XS** del prodotto https://www2.hm.com/it_it/productpage.1333421001.html
e invia un'email a **gienni.doria@gmail.com** tramite Gmail SMTP quando risulta acquistabile.

## Attivazione

1. Pubblica questi file sul branch predefinito del repository.
2. In **Settings → Secrets and variables → Actions → New repository secret**, aggiungi:
   - `GMAIL_USERNAME`: indirizzo Gmail del mittente.
   - `GMAIL_APP_PASSWORD`: password per app Google del mittente, non la password normale.
3. Per creare la password per app, attiva la verifica in due passaggi e segui
   https://support.google.com/accounts/answer/185833. Alcuni account non supportano password per app.
4. In **Actions → Controlla XS H&M → Run workflow**, esegui prima con `dry_run` attivo.
   Disattivalo per consentire l'invio se XS è disponibile.

Il controllo pianificato gira ogni 30 minuti (ai minuti 17 e 47, UTC), con possibili ritardi
di GitHub. **Invia un'email a ogni controllo positivo**, quindi può inviare più avvisi
mentre XS resta disponibile. Disabilita il workflow dopo l'acquisto.
I workflow pianificati nei repository pubblici possono essere disabilitati dopo 60 giorni di inattività.

## Esecuzione locale

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
python check_stock.py --dry-run
python -m unittest -v
```

Per l'invio locale imposta `GMAIL_USERNAME` e `GMAIL_APP_PASSWORD` nell'ambiente.
Non inserire credenziali nei file o nei commit.

### Prova con Chrome installato e sessione persistente

Se Chrome normale apre il prodotto ma Chromium automatico riceve 403, prova un
profilo dedicato. Il primo comando apre Chrome senza automazione per inizializzare
la sessione; non esegue il controllo e non invia email.

```powershell
python check_stock.py --browser chrome --profile .hm-chrome --init-session
```

Nel Chrome appena aperto visita il prodotto, gestisci il consenso cookie e verifica
che siano visibili le taglie. Non è necessario accedere all'account H&M.
**Chiudi tutte le finestre di quel profilo**, poi esegui:

```powershell
python check_stock.py --browser chrome --profile .hm-chrome --headed --dry-run
```

La cartella `.hm-chrome` contiene cookie e dati di sessione ed è esclusa da Git.
Usa solo questo profilo dedicato, non la cartella del tuo profilo Chrome personale.
Questa modalità è un tentativo: il sito può ancora bloccare il browser automatico.
La sessione resta sul PC: non viene trasferita ai runner GitHub e il workflow cloud
rimane invariato. Se il controllo locale funziona, si potrà configurare un runner
self-hosted sullo stesso PC.

Il controllo stampa subito `Controllo avviato` e poi ogni fase. L'avvio del browser
ha un limite di 30 secondi, la navigazione di 60 e la ricerca di ciascun selettore
di 45. Se fallisce, consulta l'ultimo messaggio e i file in `artifacts/`.
Se si ferma su `Avvio chrome`, chiudi tutte le finestre del profilo `.hm-chrome`.

### Collegamento a Chrome aperto normalmente

Se l'avvio tramite Playwright continua a ricevere 403, chiudi le finestre del
profilo dedicato, poi aprilo normalmente con la porta di debug locale:

```powershell
python check_stock.py --browser chrome --profile .hm-chrome --init-session --cdp
```

Verifica che il prodotto e le taglie siano visibili nella nuova finestra e lascia
aperta una sola scheda con l'URL esatto del prodotto. Poi, nello stesso PowerShell:

```powershell
python -u check_stock.py --cdp --dry-run
```

Il controllo si collega al browser aperto e usa la scheda esistente senza
ricaricarla, poi lascia aperto Chrome. La porta 9222 è configurata su localhost;
usa il profilo dedicato e chiudilo quando finisci il test. Questo tentativo non è
stato verificato sul prodotto reale: il controllo CDP termina con `XS: esaurita`.
Non rende operativi i runner cloud; la consegna SMTP resta da verificare.

## Limiti

Il controllo usa un browser Chromium, seleziona XS e verifica che il pulsante di acquisto
sia abilitato. Non aggiunge prodotti al carrello. Controlli ambigui, blocchi del sito e
modifiche ai selettori generano un errore del workflow; non vengono considerati disponibilità.
In caso di errore vengono salvati screenshot e HTML nell'artefatto `hm-diagnostics`.
Il sito può bloccare anche i runner GitHub: il test manuale iniziale serve a verificarlo.

Verifica: i test automatici sono passati. Il controllo locale riceve HTTP 403;
su GitHub Linux anche Chromium con interfaccia sotto Xvfb riceve una pagina
intermedia HTTP 200 che dopo JavaScript diventa `Access Denied`. Il workflow usa
ora `--headed` sotto Xvfb, ma questo non ha risolto il blocco del sito.
La lettura della taglia XS nella scheda reale è stata verificata con la modalità
CDP (`XS: esaurita`); la consegna SMTP resta da verificare.

Il workflow manuale **Diagnostica accesso H&M** confronta Chromium standard e
Chromium completo con un profilo browser su Linux e Windows. Legge titolo e
contenuto dopo JavaScript e salva gli artefatti: un risultato verde della diagnostica
significa che il test è stato eseguito, non che H&M abbia consentito l'accesso.
