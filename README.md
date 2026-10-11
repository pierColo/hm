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

## Limiti

Il controllo usa un browser Chromium, seleziona XS e verifica che il pulsante di acquisto
sia abilitato. Non aggiunge prodotti al carrello. Controlli ambigui, blocchi del sito e
modifiche ai selettori generano un errore del workflow; non vengono considerati disponibilità.
In caso di errore vengono salvati screenshot e HTML nell'artefatto `hm-diagnostics`.
Il sito può bloccare anche i runner GitHub: il test manuale iniziale serve a verificarlo.

Verifica locale: i test unitari sono passati, ma il controllo reale con Chromium ha
ricevuto HTTP 403 da H&M. La lettura della disponibilità sul sito reale e la consegna
SMTP non sono quindi ancora verificate. Servono un'esecuzione riuscita su Actions
e i secret Gmail prima di considerare il monitor operativo.
