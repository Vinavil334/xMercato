# Roadmap

Ipotesi: lavoro nel tempo libero, **5-6 ore a settimana**. Fino all'app pubblica (fase 5) sono circa
**4-5 mesi**. Le durate sono stime, non impegni: le fasi 2 e 4 sono quelle con più incognite.

L'ordine segue le dipendenze: prima ciò che funziona con meno dati (la classifica), per ultimo ciò che
dipende da tutto il resto (i suggerimenti di mercato). Ogni fase finisce con qualcosa che si può mostrare
e con una verifica sul passato.

| Fase | Contenuto | Durata | Finita quando |
|---|---|---|---|
| **0. Fondamenta** | Repo, CI, struttura dati, caricamento risultati, simulatore di base | 1-2 sett. | *In buona parte fatta.* Mancano i caricatori Transfermarkt e Understat |
| **1. Classifica** | Forza da xG, peso alle partite recenti, Dixon-Coles, stima pre-stagionale dal valore della rosa | 2-3 sett. | Verifica su 10 stagioni: log-loss per partita confrontata con le quote dei bookmaker; errore sui punti finali |
| **2. Anagrafica e proiezioni** | Collegamento degli ID tra le fonti; tabella giocatore-stagione; Marcel; modello dei minuti; coefficienti di campionato | 4-5 sett. | Almeno il 95% dei minuti di Serie A collegato tra Understat e Transfermarkt; errore inferiore a "uguale all'anno scorso" |
| **3. Valore** | Valore equo oggi e valore a 12 mesi | 2-3 sett. | Errore per fasce di valore, confrontato con "resta uguale, corretto per l'età" |
| **4. Mercato** | Fabbisogno per ruolo, plausibilità, probabilità di buon acquisto, lista per club | 5-6 sett. | Verifica su un'estate passata; curva di calibrazione pubblicata |
| **5. App e automazione** | App Streamlit a tre pagine (giocatore, club, campionato), aggiornamento settimanale, pagina "come funziona" con i risultati delle verifiche | 2-3 sett. | App online, dati che si aggiornano da soli |
| **6. Notizie** | Raccolta dei feed, riconoscimento di giocatori e club, stadio della voce, affidabilità delle fonti | 3-4 sett. | 200 titoli etichettati a mano e accuratezza misurata |
| **7. Simulatore tra amici** | API, login, mercato a turni, stagione simulata | Aperta | Una lega di prova giocata fino in fondo |

## Rischi principali

| Rischio | Probabilità | Cosa si fa |
|---|---|---|
| Il dataset Transfermarkt resta fermo | Media | Decidere entro la fase 2 se raccogliere da soli le rose delle 20 squadre (vedi [STUDIO.md](STUDIO.md#domande-aperte)) |
| Understat cambia formato o chiude | Media | Copia locale di tutto lo scaricato; i modelli continuano a funzionare con l'ultimo dato disponibile |
| Collegare gli ID richiede più del previsto | Alta | File di correzioni manuali; partire dalla sola Serie A e allargare dopo |
| I modelli non battono i riferimenti semplici | Media | È un risultato onesto e pubblicabile: si mostra il riferimento e si spiega perché |
| Il progetto si allarga troppo | Alta | Niente fase nuova finché la precedente non ha la sua verifica |

## Prossimi tre passi

1. Rispondere alle [domande aperte](STUDIO.md#domande-aperte), soprattutto la definizione di "buon acquisto" e la scelta sui dati Transfermarkt.
2. Caricatore Understat per la Serie A (xG per partita) e confronto gol contro xG nel modello della classifica.
3. Caricatore del dataset Transfermarkt in DuckDB, con la prima tabella giocatore-stagione.
