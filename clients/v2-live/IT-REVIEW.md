# Italian review list for V2 Live

## Phone foundation (F0) - 2026-10-28

Status: to review. New pairs in `js/i18n-phone.js` (the bottom sheet's handle button). The bar, Places and Stop strings in `js/phone-model.js` are not shown yet; the slices that draw them add their Italian.

| English | Italian |
|---|---|
| Expand | Espandi |
| Collapse | Comprimi |

## Replay structure redesign — 2026-10-27

Status: to review. New pairs in `js/i18n.js`; Italian has not been checked by a native speaker.

| English | Italian |
|---|---|
| Timeline overview | Panoramica della cronologia |
| Recorded events | Eventi registrati |
| Source record | Record di origine |
| Reference and limits | Riferimenti e limiti |
| Close evidence | Chiudi le prove |
| Inspect selected event | Esamina l’evento selezionato |
| No events in this category. | Nessun evento in questa categoria. |
| Read-only history. Select an event to inspect what Core recorded. | Cronologia in sola lettura. Seleziona un evento per esaminare ciò che il Core ha registrato. |
| Recovery proposals · SIMULATED | Proposte di recupero · SIMULATO |
## Security posture redesign — 2026-10-27

Status: **to review**. Source: `js/i18n-areas.js`. Existing fixture content and existing translations are reused.

| English | Italian |
| --- | --- |
| Needs a decision now | Decisioni da prendere ora |
| What Archeus may do | Cosa può fare Archeus |
| Boundaries | Confini |
| Recent security events | Eventi di sicurezza recenti |
| Emergency controls | Controlli di emergenza |
| Nothing is blocked | Nessun blocco attivo |
| New starts are blocked | Nuovi avvii bloccati |
| Emergency stop engaged | Arresto di emergenza attivo |
| 1 action is waiting for your decision | 1 azione attende la tua decisione |
| {n} actions are waiting for your decision | {n} azioni attendono la tua decisione |
| Physical isolation is not built | Isolamento fisico non realizzato |
| A started CLI still runs as your user. Policy does not physically confine it. | Una CLI avviata usa ancora la tua identità. La policy non la confina fisicamente. |
| Held commands never auto-allow. | I comandi in attesa non vengono mai autorizzati automaticamente. |
| Ask me each time | Chiedimi ogni volta |
| Allow once | Consenti una volta |
| Deny | Nega |
| No per-project command overrides are recorded. | Non sono registrate eccezioni ai comandi per singolo progetto. |
| Last check | Ultimo controllo |
| Execution isolation | Isolamento delle esecuzioni |
| Accounts and homes | Account e cartelle personali |
| Network | Rete |
| More boundary evidence | Altre prove sui confini |
| Held actions will appear here when a command needs your permission. | Qui appariranno le azioni in attesa quando un comando richiede il tuo permesso. |
| Security events will appear here when an action is held, decided, or stopped. | Qui appariranno gli eventi di sicurezza quando un’azione viene sospesa, decisa o fermata. |
| No projects are recorded. | Nessun progetto registrato. |
| Approval mode | Modalità di approvazione |
| Policy applies to every project below. | La policy si applica a ogni progetto qui sotto. |
| Command policy applies inside an execution. Plan only never starts one. | La policy dei comandi vale all’interno di un’esecuzione. La modalità Solo piano non ne avvia nessuna. |
| Latest events | Ultimi eventi |
| Re-armed: new work can start again. | Riarmato: il nuovo lavoro può ripartire. |
| Hook | Hook |
| Spawn breaker | Interruttore di avvio |
| Allow this action once? {consequence} No Undo. | Consentire questa azione una volta? {consequence, existing translation when available} Non si può annullare. |
| Deny this action? The execution ends and the mission is blocked. No Undo. | Negare questa azione? L’esecuzione termina e la missione viene bloccata. Non si può annullare. |
| {policy state} / {physical state} | {existing Italian policy state} / {existing Italian physical state} |

Every Italian string in V2 Live was written by the builders (there is no native source). All 1364 pairs below are **to review**. English is the source; fixture words that stand in for Core's own text (mission titles, branches, project names, tool names, Replay categories) and the terminal view's program text stay English by design.

Where a pair is a pattern (a number or name inside the sentence) the dictionary also holds regex rules in `js/i18n.js` and `js/i18n-areas.js` (`RULES`); those are not listed pair by pair here. Core state words (Waiting for approval, Executing, ...) come from `core-words.js` and are English in Core; their Italian is in the dictionary above.

How to review: change the Italian in the named file, run `node --test clients/v2-live/test/*.test.mjs`, and the IT layout probe (`py tools\v2_live_layout_probe.py --lang it`) to see that the longer text still fits.

## Main dictionary: shell

Status: to review. 45 strings.

| English | Italian |
|---|---|
| Now | Adesso |
| Work | Lavoro |
| Attention | Attenzione |
| Settings | Impostazioni |
| More | Altro |
| Security | Sicurezza |
| Health | Stato di salute |
| Accounts | Account |
| Terminal view | Vista terminale |
| Terminal | Terminale |
| All devices | Tutti i dispositivi |
| Device | Dispositivo |
| Theme | Tema |
| Motion | Movimento |
| Quiet | Quieto |
| Paused | In pausa |
| Language | Lingua |
| Notes | Note |
| Phone | Telefono |
| Dark | Scuro |
| Light | Chiaro |
| Dark, high contrast | Scuro, alto contrasto |
| Light, high contrast | Chiaro, alto contrasto |
| System | Sistema |
| Forced colours (simulated) | Colori forzati (simulati) |
| Dark HC | Scuro AC |
| Light HC | Chiaro AC |
| Forced colours | Colori forzati |
| Fills the window | Riempie la finestra |
| Text mode | Modalità testo |
| SIMULATED | SIMULATO |
| no Core connected | nessun Core collegato |
| Prototype controls | Controlli del prototipo |
| Device preview | Anteprima dispositivo |
| Reduced motion | Movimento ridotto |
| Simulation | Simulazione |
| V2 Live prototype. Simulated. No Core is connected. | Prototipo V2 Live. Simulato. Nessun Core collegato. |
| Main | Principale |
| Details | Dettagli |
| Expand or collapse the navigation | Apri o chiudi la navigazione |
| A frame shows the real app at that width inside this page. If the window is narrower, the frame is scaled down to fit. | Un riquadro mostra l'app vera a quella larghezza dentro la pagina. Se la finestra è più stretta, il riquadro viene ridotto. |
| System follows the OS (including high contrast). Forced colours is a simulation; the real forced-colors mode is also honoured. | Sistema segue il sistema operativo (anche l'alto contrasto). I colori forzati sono una simulazione; anche la vera modalità forced-colors è rispettata. |
| Decision notes | Note sulle decisioni |
| Show which decision each choice implements | Mostra quale decisione attua ogni scelta |

## Main dictionary: page heads

Status: to review. 2 strings.

| English | Italian |
|---|---|
| (paused) | (in pausa) |

## Main dictionary: Now

Status: to review. 22 strings.

| English | Italian |
|---|---|
| The sentence is built only from Core state words and counts. | La frase è costruita solo con parole di stato del Core e conteggi. |
| Live map | Mappa viva |
| vector, redrawn at every size | vettoriale, ridisegnata a ogni dimensione |
| Happening now | In corso adesso |
| Upcoming | In arrivo |
| Recent decisions and changes | Decisioni e cambiamenti recenti |
| Nothing is waiting for a decision. | Nessuna decisione in attesa. |
| Nothing is running. | Niente in esecuzione. |
| Nothing is planned or approved. | Niente di pianificato o approvato. |
| Nothing has changed yet. | Non è cambiato ancora nulla. |
| Project | Progetto |
| Mission | Missione |
| Execution | Esecuzione |
| Decision | Decisione |
| Centre: Core,  | Centro: Core,  |
| nothing running | niente in esecuzione |
| Open decision | Apri la decisione |
| Open review | Apri la revisione |
| Open | Apri |
| Open Settings | Apri Impostazioni |
| Open Replay | Apri Replay |
| Open the terminal view | Apri la vista terminale |

## Main dictionary: Work

Status: to review. 3 strings.

| English | Italian |
|---|---|
| Ideas | Idee |
| Blocked | Bloccata |
| Needs you | Richiede te |

## Main dictionary: Attention

Status: to review. 17 strings.

| English | Italian |
|---|---|
| Decide | Decidi |
| Review | Rivedi |
| Unblock | Sblocca |
|  u00b7 asks you to decide |  u00b7 ti chiede di decidere |
|  u00b7 results to accept |  u00b7 risultati da accettare |
|  u00b7 work that needs a person |  u00b7 lavoro che richiede una persona |
| asks you to decide | ti chiede di decidere |
| results to accept | risultati da accettare |
| work that needs a person | lavoro che richiede una persona |
| Nothing waits on you. | Niente aspetta te. |
| Remember | Ricorda |
| Not this | Non questo |
| Re-enable | Riattiva |
| Approve | Approva |
| Reject | Rifiuta |
| Candidate | Candidato |
| Automation | Automazione |

## Main dictionary: inspector and decision

Status: to review. 35 strings.

| English | Italian |
|---|---|
| Close | Chiudi |
| Close details | Chiudi i dettagli |
| Close decision | Chiudi la decisione |
| Outcome | Esito |
| Plan | Piano |
| Evidence | Prove |
| Timeline | Cronologia |
| Where it is | A che punto è |
| Facts | Fatti |
| State | Stato |
| Branch | Ramo |
| Origin | Origine |
| Tasks | Attività |
| Why | Perché |
| Executions | Esecuzioni |
| Plan versions | Versioni del piano |
| Verification | Verifica |
| Last recorded steps | Ultimi passi registrati |
| Mission steps | Passi della missione |
| No plan yet. | Ancora nessun piano. |
| No execution yet. | Ancora nessuna esecuzione. |
| Nothing has been verified yet. | Ancora nulla è stato verificato. |
| Answer and unblock | Rispondi e sblocca |
| Cancel mission | Annulla la missione |
| Resume | Riprendi |
| Replan | Ripianifica |
| Accept | Accetta |
| Request changes | Chiedi modifiche |
| Pause | Pausa |
| Approve this plan? | Approvare questo piano? |
| Allow this action? | Consentire questa azione? |
| What | Cosa |
| Why it asks | Perché lo chiede |
| What Core does next | Cosa fa il Core dopo |
| Where the mission is | A che punto è la missione |

## Main dictionary: spine

Status: to review. 9 strings.

| English | Italian |
|---|---|
| Understanding | Comprensione |
| Understand | Capisci |
| Run | Esegui |
| Verify | Verifica |
| Approval | Approvazione |
| Executing | Esecuzione |
| Verifying | Verifica |
| Reviewing | Revisione |
| Position unknown | Posizione sconosciuta |

## Main dictionary: mission/other state words

Status: to review. 21 strings.

| English | Italian |
|---|---|
| Created | Creata |
| Context gathering | Raccolta del contesto |
| Reasoning | Ragionamento |
| Replanning | Ripianificazione |
| Waiting for approval | In attesa di approvazione |
| Approved u2014 not started | Approvata u2014 non avviata |
| Resuming | Ripresa |
| Reviewing u2014 verified, not accepted | In revisione u2014 verificata, non accettata |
| Failed | Fallita |
| Done u2014 verified and reviewed | Fatta u2014 verificata e rivista |
| Cancelled | Annullata |
| Running | In esecuzione |
| Starting | Avvio |
| Awaiting approval | In attesa di approvazione |
| Lost u2014 Core is reconciling | Persa u2014 il Core sta riconciliando |
| Exited ok u2014 not verified | Uscita ok u2014 non verificata |
| Ended error | Finita con errore |
| Pending | In sospeso |
| Approved | Approvata |
| Rejected | Rifiutata |
| Passed | Superata |

## Main dictionary: statuses of other machines used on the main surfaces

Status: to review. 5 strings.

| English | Italian |
|---|---|
| Planned | Pianificata |
| Parked | Parcheggiata |
| Explored | Esplorata |
| Scheduled | Programmata |
| Captured | Catturata |

## Main dictionary: Replay

Status: to review. 33 strings.

| English | Italian |
|---|---|
| Approve plan | Approva il piano |
| Allow action | Consenti l'azione |
| Done | Fatta |
| Idle | Inattiva |
| Thinking | In pianificazione |
| Knowledge | Conoscenza |
| Node | Nodo |
| Kind | Tipo |
| Unassigned | Senza progetto |
| Live map of your projects and missions. The list beside it has the same content. | Mappa viva dei tuoi progetti e delle tue missioni. L'elenco accanto ha lo stesso contenuto. |
| Constellation nodes. Select a row to focus its star. | Nodi della costellazione. Scegli una riga per portare il focus sulla sua stella. |
| Map view | Vista della mappa |
| Zoom out | Riduci |
| Zoom in | Ingrandisci |
| Fit all nodes | Mostra tutti i nodi |
| Reset map view | Ripristina la vista |
| Fit | Adatta |
| Selected step | Passo selezionato |
| Categories | Categorie |
| Not recorded | Non registrato |
| Earlier | Prima |
| Later | Dopo |
| Step | Passo |
| Time | Ora |
| Category | Categoria |
| Trigger | Causa |
| Settled by | Chiuso da |
| Record | Registro |
| What Core recorded, in order. Each step carries a Replay category and who settled it. Nothing here can be re-run. | Ciò che il Core ha registrato, in ordine. Ogni passo ha una categoria Replay e chi lo ha chiuso. Qui nulla può essere rieseguito. |
| Older steps were pruned from the event log, so anything before them is UNKNOWN, not "nothing happened". | I passi più vecchi sono stati eliminati dal registro eventi, quindi ciò che li precede è SCONOSCIUTO, non "non è successo nulla". |
| No recorded steps for this mission. | Nessun passo registrato per questa missione. |
| Nothing selected. | Niente di selezionato. |

## Main dictionary: Chat

Status: to review. 12 strings.

| English | Italian |
|---|---|
| Conversation | Conversazione |
| every reply is scripted and labelled | ogni risposta è scritta in anticipo ed etichettata |
| Send | Invia |
| Message to Archeus | Messaggio ad Archeus |
| Tell Archeus what you need... | Dì ad Archeus di cosa hai bisogno... |
| You | Tu |
| Slash commands: type "/" for the list. READ and CREATE commands act at once; PROPOSE commands only make a card you confirm. Nothing you type leaves this page. | Comandi con slash: scrivi "/" per l'elenco. I comandi READ e CREATE agiscono subito; i comandi PROPOSE fanno solo una scheda da confermare. Nulla di ciò che scrivi esce da questa pagina. |
| Confirm | Conferma |
| Dismiss | Scarta |
| Confirmed | Confermato |
| Dismissed | Scartato |
| Commands | Comandi |

## Main dictionary: Settings and the new areas

Status: to review. 33 strings.

| English | Italian |
|---|---|
| Appearance | Aspetto |
| Motion  | Movimento  |
| Follow the system | Segui il sistema |
| Full | Pieno |
| Reduced (Quiet) | Ridotto (Quieto) |
| Play | Avvia |
| Speed | Velocità |
| Trigger an approval | Genera una richiesta |
| Inject a failure | Inietta un guasto |
| Break the harness | Rompi l'harness |
| Reset | Ripristina |
| Accounts and usage | Account e utilizzo |
| 5 hour window | Finestra di 5 ore |
| Week | Settimana |
| Models and harnesses | Modelli e harness |
| Automations | Automazioni |
| Hooks, MCP servers and agents | Hook, server MCP e agenti |
| Clients | Client |
| About this prototype | Informazioni su questo prototipo |
| unknown | sconosciuto |
| Spawn breaker | Interruttore di avvio |
| Isolation and switches | Isolamento e interruttori |
| Checks | Controlli |
| Owner decisions | Decisioni del proprietario |
| Not closed | Non chiuso |
| Built, switch off | Costruito, interruttore spento |
| Off | Spento |
| Built | Costruito |
| Closed | Chiuso |
| Open: cannot start | Aperto: non può avviare |
| attention | attenzione |
| Everything here | Tutto qui |
| Go to | Vai a |

## Main dictionary: slash command descriptions (aliases are listed next to the n

Status: to review. 36 strings.

| English | Italian |
|---|---|
| List the commands by class | Elenca i comandi per classe |
| What is running, waiting and stopped | Cosa è in corso, in attesa e fermo |
| Usage of the accounts (unknown until the read exists) | Utilizzo degli account (sconosciuto finché la lettura non esiste) |
| The projects | I progetti |
| The missions, optionally of one project | Le missioni, eventualmente di un progetto |
| What waits for you | Cosa aspetta te |
| The ideas | Le idee |
| Open the Replay of a mission | Apri il Replay di una missione |
| Open a mission | Apri una missione |
| Create a mission (it waits for your approval here) | Crea una missione (qui aspetta la tua approvazione) |
| Capture an idea | Cattura un'idea |
| Propose pausing a mission | Proponi di mettere in pausa una missione |
| Propose resuming a mission | Proponi di riprendere una missione |
| Propose cancelling a mission | Proponi di annullare una missione |
| Open the decision; it decides nothing | Apri la decisione; non decide nulla |
| Propose an emergency stop of every running mission | Proponi un arresto d’emergenza di ogni missione in corso |
|  ti serve |  ti servono |
|  fermo |  fermi |
| Changes requested | Modifiche richieste |
| Not remembered | Non ricordato |
| Pause, resume and emergency stop | Pausa, ripresa e arresto d’emergenza |
| Pause all | Metti tutto in pausa |
| Resume all | Riprendi tutto |
| Emergency stop | Arresto d’emergenza |
| Yes, stop everything | Sì, ferma tutto |
| Re-arm | Riarma |
| Yes, re-arm | Sì, riarma |
| A vector constellation drawn from the simulation and redrawn at every size. Selecting a star opens it; the list beside it is the text mirror with the same content. | Una costellazione vettoriale disegnata dalla simulazione e ridisegnata a ogni dimensione. Selezionare una stella la apre; l’elenco accanto è lo specchio testuale con lo stesso contenuto. |
| The shell, the map, the mission and decision views, chat, Replay and the terminal view are built on the simulation. A Core connection, real accounts and the native apps are not built. | La struttura, la mappa, le viste di missione e decisione, la chat, il Replay e la vista terminale sono costruiti sulla simulazione. La connessione a un Core, gli account reali e le app native non sono costruiti. |
| The emergency stop is engaged: nothing new starts and no mission resumes until you re-arm. Re-arming needs a step-up (simulated here). | L’arresto d’emergenza è attivo: non parte nulla di nuovo e nessuna missione riprende finché non riarmi. Riarmare richiede una conferma rafforzata (simulata qui). |
| Re-armed: new work can start again (simulated). | Riarmato: il nuovo lavoro può ripartire (simulato). |
| Show all projects | Mostra tutti i progetti |
| Project filter | Filtro progetto |
| Pausing every running mission (simulated). | Metto in pausa ogni missione in corso (simulato). |
| Resuming every paused mission (simulated). | Riprendo ogni missione in pausa (simulato). |
| Emergency stop: every running mission stopped, new dispatch blocked until re-armed (simulated). | Arresto d’emergenza: ogni missione in corso è ferma, ogni nuovo avvio bloccato finché non riarmi (simulato). |

## Areas dictionary: routes and areas

Status: to review. 28 strings.

| English | Italian |
|---|---|
| Usage | Utilizzo |
| Extensions | Estensioni |
| Accounts and models | Account e modelli |
| Hooks | Hook |
| MCP servers | Server MCP |
| Agents | Agenti |
| Models | Modelli |
| Failover rules | Regole di subentro |
| Launch settings per project | Impostazioni di avvio per progetto |
| Spawn breakers | Interruttori di avvio |
| Switches | Interruttori |
| Security log | Registro di sicurezza |
| Owner rules | Regole del proprietario |
| Two boundaries | Due confini |
| Eight boundaries | Otto confini |
| What is isolated and what is not | Cosa è isolato e cosa no |
| What an execution may do | Cosa può fare un’esecuzione |
| Pinned | Fissate |
| Pin | Fissa |
| Unpin | Rimuovi |
| Mark as seen | Segna come visto |
| Today | Oggi |
| Since you last looked | Da quando hai guardato l’ultima volta |
| Digest range | Intervallo del riepilogo |
| Reconnect | Riconnetti |
| Go offline | Vai offline |
| Idea path | Percorso dell’idea |
| Readings | Letture |

## Areas dictionary: pills and states

Status: to review. 57 strings.

| English | Italian |
|---|---|
| Needs attention | Richiede attenzione |
| Need attention | Richiedono attenzione |
| Unknown | Sconosciuto |
| Not built | Non costruito |
| Designed | Progettato |
| Partly | In parte |
| Open | Aperto |
| Designed, not built | Progettato, non costruito |
| Designed, switches off | Progettato, interruttori spenti |
| HTTP side built, switch off | Lato HTTP costruito, interruttore spento |
| Closed: starts normally | Chiuso: parte normalmente |
| Half open | Semiaperto |
| Not installed | Non installato |
| Not installed on this machine. | Non installato su questa macchina. |
| Allowed | Consentito |
| Asks you | Ti chiede |
| Denied | Negato |
| Denied by policy only | Negato solo dalla policy |
| Unguarded | Senza guardia |
| Not confined | Non confinato |
| Asks | Chiede |
| Passed | Superato |
| Failed | Fallito |
| Enabled | Attivo |
| Disabled | Disattivo |
| Connected | Connesso |
| Connecting | Connessione |
| Suspended | Sospesa |
| Pending approval | In attesa di approvazione |
| Revoked | Revocato |
| Built in | Integrato |
| Always on | Sempre attivo |
| Not checked | Non verificato |
| Working | In lavoro |
| Idle | Inattivo |
| On | Acceso |
| Result waits | Risultato in attesa |
| Can start | Può avviare |
| Cannot start | Non può avviare |
| Waits | In attesa |
| On track | In regola |
| Low | Basso |
| Almost out | Quasi esaurito |
| Limit reached | Limite raggiunto |
| Default | Predefinito |
| Default model | Modello predefinito |
| Not the default | Non predefinito |
| Chosen | Scelto |
| Passed over | Scartato |
| Not eligible | Non idoneo |
| Needs a person | Richiede una persona |
| Available | Disponibile |
| Near its ceiling | Vicino al limite |
| Unverified | Non verificato |
| Yes | Sì |
| Never | Mai |
| None | Nessuno |

## Areas dictionary: security

Status: to review. 93 strings.

| English | Italian |
|---|---|
| Policy boundary | Confine di policy |
| Physical isolation | Isolamento fisico |
| Spawn breakers closed | Interruttori di avvio chiusi |
| Five rules hold today | Cinque regole valgono oggi |
| Every harness starts normally | Ogni harness parte normalmente |
| Archeus stops what policy can stop. It does not yet confine a running process at the operating system level, and this page says so. | Archeus ferma ciò che la policy può fermare. Non confina ancora un processo in esecuzione a livello di sistema operativo, e questa pagina lo dice. |
| Neither stands in for the other. | Nessuno dei due sostituisce l’altro. |
| Application policy | Policy applicativa |
| Physical reach | Raggio d’azione fisico |
| What Archeus lets a run do: the workdir, the stripped environment, the fail-closed hook, approvals. This is V1 today. | Ciò che Archeus permette a un’esecuzione: la cartella di lavoro, l’ambiente ripulito, l’hook che nega per impostazione predefinita, le approvazioni. È la V1 di oggi. |
| What a process can physically reach, whatever the agent tries: an isolated identity, AppContainer, job object, ACLs. Gated off. | Ciò che un processo può raggiungere fisicamente, qualunque cosa tenti l’agente: identità isolata, AppContainer, job object, ACL. Disattivato. |
| Held by policy, and the gaps that policy cannot close. | Ciò che la policy garantisce, e le lacune che non può chiudere. |
| Held by policy | Garantito dalla policy |
| Not isolated | Non isolato |
| Credentials: Archeus never reads, stores, copies, injects or relays subscription tokens. | Credenziali: Archeus non legge, conserva, copia, inietta né inoltra mai i token degli abbonamenti. |
| Environment: prompts off, askpass empty, no ssh agent, no credential helper. | Ambiente: richieste spente, askpass vuoto, nessun agente ssh, nessun gestore di credenziali. |
| Writes outside the workdir are denied by a fail-closed hook. | Le scritture fuori dalla cartella di lavoro sono negate da un hook che nega per impostazione predefinita. |
| Risky actions ask you first: a push, a package install, a delete. | Le azioni rischiose ti chiedono prima: un push, l’installazione di un pacchetto, una cancellazione. |
| Approvals are scoped: deciding needs the approve scope, and chat only opens a card. | Le approvazioni hanno un ambito: decidere richiede l’ambito di approvazione, e la chat apre solo una scheda. |
| A started CLI runs as your user. It can reach your profile, home and credential stores, because the OS does not stop it (finding G1, critical). | Una CLI avviata gira come tuo utente. Può raggiungere il tuo profilo, la home e gli archivi di credenziali, perché il sistema operativo non la ferma (rilievo G1, critico). |
| Network access is not confined. Provider access is not yet brokered: the broker is built and switched off. | L’accesso alla rete non è confinato. L’accesso al provider non passa ancora da un broker: il broker è costruito e spento. |
| Another execution is not walled off at the OS level. | Un’altra esecuzione non è isolata a livello di sistema operativo. |
| No process has ever been started under isolation by production code. The dispatch switch is off. | Nessun processo è mai stato avviato in isolamento dal codice di produzione. L’interruttore di avvio è spento. |
| The verifier is not confined. | Il verificatore non è confinato. |
| Each with its policy layer and its physical layer. | Ciascuno con il suo livello di policy e il suo livello fisico. |
| Physical | Fisico |
| Policy layer | Livello di policy |
| Verifier | Verificatore |
| User | Utente |
| Deputy | Delegato |
| The identity a run starts under, its job object and its own files. | L’identità con cui parte un’esecuzione, il suo job object e i suoi file. |
| The confined identity that runs verification commands. | L’identità confinata che esegue i comandi di verifica. |
| Provider access through Core, never from the run itself. | Accesso al provider tramite il Core, mai dall’esecuzione stessa. |
| Split-authority mailbox and the effect boundary. | Casella a autorità divisa e confine degli effetti. |
| Your profile, home and credential stores (finding G1, critical). | Il tuo profilo, la home e gli archivi di credenziali (rilievo G1, critico). |
| Which process connects, and other executions. | Quale processo si connette, e le altre esecuzioni. |
| Forwarding hops and the remote tunnel. | Inoltri intermedi e tunnel remoto. |
| Archeus code that runs as you. | Codice di Archeus che gira come te. |
| Policy denies a run these stores, but a started process still runs as your user and the OS does not stop it. This is the critical hole that P20 must close. | La policy nega questi archivi a un’esecuzione, ma un processo avviato gira comunque come tuo utente e il sistema operativo non lo ferma. È il buco critico che P20 deve chiudere. |
| What this means | Cosa significa |
| Status | Stato |
| Boundary · B5 | Confine · B5 |
| As the board records it on 2026-10-21. Nothing here is simulated as working: the physical layer is not built in V1. | Come lo registra la bacheca il 2026-10-21. Nulla qui è simulato come funzionante: il livello fisico non è costruito nella V1. |
| One per CLI. Trips at 3 failed starts in 10 minutes. | Uno per CLI. Scatta con 3 avvii falliti in 10 minuti. |
| Starts normally. | Parte normalmente. |
| A waiting task backs off 15 s, 30 s, 1 min, 2 min, 4 min, then 5 min. After 5 minutes one trial start is allowed. It never falls back to an unisolated run. | Un’attività in attesa ritarda di 15 s, 30 s, 1 min, 2 min, 4 min, poi 5 min. Dopo 5 minuti è consentito un solo avvio di prova. Non ripiega mai su un’esecuzione non isolata. |
| Trip the breaker | Fai scattare l’interruttore |
| Reset the breaker | Reimposta l’interruttore |
| Back | Indietro |
| Failed starts | Avvii falliti |
| Installed | Installato |
| Breaker | Interruttore |
| How it works | Come funziona |
| Trips at 3 failed starts in 10 minutes. A waiting task backs off 15 s, 30 s, 1 min, 2 min, 4 min, then 5 min. After 5 minutes one trial start is allowed. It never falls back to an unisolated run. | Scatta con 3 avvii falliti in 10 minuti. Un’attività in attesa ritarda di 15 s, 30 s, 1 min, 2 min, 4 min, poi 5 min. Dopo 5 minuti è consentito un solo avvio di prova. Non ripiega mai su un’esecuzione non isolata. |
| Production dispatch of isolated runs | Avvio in produzione di esecuzioni isolate |
| A constant false in V1. No isolated process has been started by production code. | Una costante falsa nella V1. Nessun processo isolato è stato avviato dal codice di produzione. |
| Provider broker | Broker del provider |
| Named pipe and bridge exist and pass fixture tests. Nothing runs them. | Named pipe e bridge esistono e superano i test con dati di esempio. Nulla li esegue. |
| Core API origin gate | Controllo di origine dell’API del Core |
| The native side is a fail-closed stub. | Il lato nativo è uno stub che nega per impostazione predefinita. |
| Emergency stop and re-arm | Arresto d’emergenza e riarmo |
| Stops every execution. Re-arming needs a step-up. | Ferma ogni esecuzione. Riarmare richiede una conferma rafforzata. |
| Stops every execution and blocks new dispatch until re-armed. Re-arming needs a step-up. | Ferma ogni esecuzione e blocca ogni nuovo avvio finché non è riarmato. Riarmare richiede una conferma rafforzata. |
| Stops every execution and blocks new dispatch until re-armed; re-arming needs a step-up. | Ferma ogni esecuzione e blocca ogni nuovo avvio finché non è riarmato; riarmare richiede una conferma rafforzata. |
| Engaged: nothing new starts | Attivo: non parte nulla di nuovo |
| Missions stay Blocked "Emergency stop" and no new dispatch starts until you re-arm (a step-up). | Le missioni restano Bloccate "Arresto d’emergenza" e non parte nessun nuovo avvio finché non riarmi (conferma rafforzata). |
| OS notification per approval and per breaker trip | Notifica del sistema per ogni approvazione e per ogni scatto dell’interruttore |
| One notification each, with no secret in the text. | Una notifica ciascuno, senza segreti nel testo. |
| Who stops each thing, and what is not stopped at all. | Chi ferma ogni cosa, e cosa non è fermato affatto. |
| Read files in its workdir | Leggere file nella sua cartella di lavoro |
| Write files in its workdir | Scrivere file nella sua cartella di lavoro |
| Run the project tests and commands | Eseguire i test e i comandi del progetto |
| Commit locally | Fare commit in locale |
| Install a package | Installare un pacchetto |
| Start another execution | Avviare un’altra esecuzione |
| Read your credential stores | Leggere i tuoi archivi di credenziali |
| Open its own network connections | Aprire connessioni di rete proprie |
| Policy. Inside the execution workdir only. | Policy. Solo dentro la cartella di lavoro dell’esecuzione. |
| Hook: keep writes inside the workdir. Anything outside is denied, and a hook that cannot answer denies. | Hook: tieni le scritture dentro la cartella di lavoro. Tutto ciò che sta fuori è negato, e un hook che non sa rispondere nega. |
| Policy. With the stripped environment. | Policy. Con l’ambiente ripulito. |
| Policy. A push is a separate action. | Policy. Il push è un’azione a parte. |
| Hook: ask before git push. Stops and asks you with the exact command. | Hook: chiedi prima di git push. Si ferma e ti chiede, con il comando esatto. |
| Policy. Asks with the package name. | Policy. Chiede indicando il nome del pacchetto. |
| Policy. Only Core dispatches. | Policy. Solo il Core avvia. |
| Policy only. Denied by policy, not by the OS: physical reach is not built (finding G1). | Solo policy. Negato dalla policy, non dal sistema operativo: il raggio d’azione fisico non è costruito (rilievo G1). |
| Not confined. Provider access is not brokered yet and the network is not walled off. | Non confinato. L’accesso al provider non passa ancora da un broker e la rete non è isolata. |
| Breakers, hooks and what you changed. | Interruttori, hook e ciò che hai cambiato. |
| Never push, never touch credentials | Mai fare push, mai toccare le credenziali |
| Archeus does not read, store, copy, inject or relay subscription tokens. | Archeus non legge, conserva, copia, inietta né inoltra i token degli abbonamenti. |
| Decisions are the owner's | Le decisioni sono del proprietario |
| Chat proposes; only a card on screen with its hash is decided. | La chat propone; si decide solo una scheda a schermo con il suo hash. |
| No silent approval | Nessuna approvazione silenziosa |
| A new mission from chat waits for a card here (V1 today starts it; flagged G1). | Una nuova missione dalla chat aspetta una scheda qui (la V1 di oggi la avvia; segnalato G1). |

## Areas dictionary: health

Status: to review. 44 strings.

| English | Italian |
|---|---|
| Health check | Controllo di salute |
| Cause | Causa |
| Fix | Soluzione |
| Nothing to fix. | Niente da correggere. |
| Open the breaker | Apri l’interruttore |
| Open Usage | Apri Utilizzo |
| Open the server | Apri il server |
| Six checks, each read from records. When one is not OK it says why and what to do. A missing reading is unknown, never 0. | Sei controlli, ciascuno letto dai registri. Quando uno non è OK dice perché e cosa fare. Una lettura mancante è sconosciuta, mai 0. |
| Core process | Processo del Core |
| Event log | Registro eventi |
| Harnesses and spawn breakers | Harness e interruttori di avvio |
| Disk space | Spazio su disco |
| OS notifications | Notifiche del sistema |
| Always up in this simulation. No real Core is connected. | Sempre attivo in questa simulazione. Nessun Core reale è collegato. |
| Readable. Events are kept for 180 days. | Leggibile. Gli eventi si conservano per 180 giorni. |
| Process | Processo |
| Up (simulated) | Attivo (simulato) |
| Plan, policy, verify and metrics workers | Worker di piano, policy, verifica e metriche |
| Automation worker | Worker delle automazioni |
| Running, 1 automation held by the loop guard | In esecuzione, 1 automazione trattenuta dalla guardia anti-ciclo |
| Kept for | Conservati per |
| 180 days | 180 giorni |
| Events in this session | Eventi in questa sessione |
| Oldest kept | Il più vecchio conservato |
| Older than that | Più vecchi |
| Unknown, never "nothing happened" | Sconosciuto, mai «non è successo nulla» |
| AVAILABLE only says the tool is installed. | AVAILABLE dice solo che lo strumento è installato. |
| Not installed (optional) | Non installato (facoltativo) |
| Closed, starts normally | Chiuso, parte normalmente |
| Wait. The breaker allows one trial start after 5 minutes and closes if it works. | Aspetta. L’interruttore consente un avvio di prova dopo 5 minuti e si chiude se funziona. |
| No reading yet. | Nessuna lettura ancora. |
| Free space | Spazio libero |
| Last reading | Ultima lettura |
| None | Nessuna |
| Core does not read the disk yet. A missing reading is shown as unknown, never as 0 bytes. | Il Core non legge ancora il disco. Una lettura mancante è mostrata come sconosciuta, mai come 0 byte. |
| Nothing to do. The reading shows up when Core records it. | Niente da fare. La lettura compare quando il Core la registra. |
| Sent in this session | Inviate in questa sessione |
| Content | Contenuto |
| No secret in the text | Nessun segreto nel testo |
| One simulated notification per approval request and per breaker trip. | Una notifica simulata per ogni richiesta di approvazione e per ogni scatto dell’interruttore. |
| Or put another account first in the failover order. | Oppure metti un altro account per primo nell’ordine di subentro. |
| Or change the line under Failover rules. | Oppure cambia la soglia nelle Regole di subentro. |
| Start one small mission on it so Core can read its usage. | Avvia una piccola missione su questo account così il Core può leggerne l’utilizzo. |
| Or reset it on Security after you check that | Oppure reimpostalo in Sicurezza dopo aver verificato che |

## Areas dictionary: usage

Status: to review. 20 strings.

| English | Italian |
|---|---|
| How much of each account is left, read only from the existing usage reader. Archeus shows a number only when it can source it. | Quanto resta di ogni account, letto solo dal lettore di utilizzo esistente. Archeus mostra un numero solo quando può documentarlo. |
| On track, more than 20% left | In regola, resta più del 20% |
| Low, 20% or less left | Basso, resta il 20% o meno |
| Almost out, 5% or less | Quasi esaurito, resta il 5% o meno |
| Unknown, never 0 | Sconosciuto, mai 0 |
| The tick is the 20% line | Il segno è la soglia del 20% |
| left | resta |
| no reading | nessuna lettura |
| On track. | In regola. |
| Reset time unknown | Orario di azzeramento sconosciuto |
| Session over the last hour | Sessione nell’ultima ora |
| First choice | Prima scelta |
| Failover | Subentro |
| Not verified | Non verificato |
| No reading yet: Core has never started this account. Unknown is not zero. | Nessuna lettura ancora: il Core non ha mai avviato questo account. Sconosciuto non vuol dire zero. |
| At or under your 20% line. New work prefers another account. | Sotto o alla tua soglia del 20%. Il nuovo lavoro preferisce un altro account. |
| Limit reached. New work uses another account. | Limite raggiunto. Il nuovo lavoro usa un altro account. |
| Almost out. New work prefers another account. | Quasi esaurito. Il nuovo lavoro preferisce un altro account. |
| These are account percentages read about every 15 minutes, not the cost or tokens of one session. | Sono percentuali dell’account lette circa ogni 15 minuti, non il costo né i token di una sessione. |
| These are account percentages, not the cost or tokens of one session. Unknown stays unknown, never 0. | Sono percentuali dell’account, non il costo né i token di una sessione. Sconosciuto resta sconosciuto, mai 0. |

## Areas dictionary: accounts

Status: to review. 37 strings.

| English | Italian |
|---|---|
| Three accounts, four models, one default, and the rules that decide which account takes the next mission. | Tre account, quattro modelli, uno predefinito, e le regole che decidono quale account prende la prossima missione. |
| In failover order. The first available account takes the next mission. | In ordine di subentro. Il primo account disponibile prende la prossima missione. |
| A subscription login belongs to you. Archeus never reads, stores, copies, injects or relays the token. | L’accesso con abbonamento è tuo. Archeus non legge, conserva, copia, inietta né inoltra mai il token. |
| What happens when an account runs low or out. | Cosa succede quando un account sta finendo o è esaurito. |
| Hand off a run when its account is limited | Passa il lavoro quando il suo account è limitato |
| The run writes a checkpoint and continues on the next account. | L’esecuzione scrive un checkpoint e prosegue sull’account successivo. |
| New work waits when the week is low | Il nuovo lavoro attende quando la settimana è bassa |
| Your line. Running work finishes; nothing new starts on that account. | La tua soglia. Il lavoro in corso finisce; su quell’account non parte nulla di nuovo. |
| Line, percent left | Soglia, percentuale rimasta |
| Ask before switching to another harness | Chiedi prima di passare a un altro harness |
| A move from Claude Code to Codex is a card you confirm. | Il passaggio da Claude Code a Codex è una scheda che confermi. |
| Never run without isolation | Mai eseguire senza isolamento |
| There is no unisolated fallback, whatever else fails. | Non esiste un ripiego senza isolamento, qualunque altra cosa fallisca. |
| The default is what a new mission asks for. | Il predefinito è ciò che chiede una nuova missione. |
| Make default | Rendi predefinito |
| This is the model Archeus asks for, not proof of which model the provider served. | È il modello che Archeus richiede, non la prova di quale modello abbia servito il provider. |
| This is the model Archeus asks for. It is not proof of which model the provider served. | È il modello che Archeus richiede. Non è la prova di quale modello abbia servito il provider. |
| What a new mission starts with, and what would happen right now. | Con cosa parte una nuova missione, e cosa succederebbe adesso. |
| Next mission:  | Prossima missione:  |
| Next mission: | Prossima missione: |
| Model | Modello |
| Approvals | Approvazioni |
| Runs at once | Esecuzioni contemporanee |
| Automatic, by failover order | Automatico, in ordine di subentro |
| Ask on risky actions | Chiedi sulle azioni rischiose |
| Plan only, never execute | Solo piano, mai eseguire |
| Approve low risk automatically | Approva da solo il rischio basso |
| Isolation: required. It cannot be switched off here. | Isolamento: obbligatorio. Qui non si può spegnere. |
| Move up | Sposta su |
| Move down | Sposta giù |
| Role | Ruolo |
| Sign in | Accesso |
| A subscription login. Archeus never reads, stores, copies, injects or relays the token. | Un accesso con abbonamento. Archeus non legge, conserva, copia, inietta né inoltra mai il token. |
| Failover order | Ordine di subentro |
| Missions using it | Missioni che lo usano |
| Tier | Livello |
| Account health states are Core's own words; the order decides which account takes the next mission. | Gli stati di salute dell’account sono parole del Core; l’ordine decide quale account prende la prossima missione. |

## Areas dictionary: extensions

Status: to review. 80 strings.

| English | Italian |
|---|---|
| What can act before, after and beside a run. Each row says its status and when it last ran; a switch changes it for the next run. | Ciò che può agire prima, dopo e accanto a un’esecuzione. Ogni riga dice il suo stato e quando è stata eseguita l’ultima volta; un interruttore la cambia per la prossima esecuzione. |
| Run before or after a tool. A hook that guards something asks you to confirm before it is switched off. | Gira prima o dopo uno strumento. Un hook che protegge qualcosa ti chiede conferma prima di essere spento. |
| Tools a run can call. A server that writes asks first. | Strumenti che un’esecuzione può chiamare. Un server che scrive chiede prima. |
| The roles Core calls. None of them can decide for you. | I ruoli che il Core chiama. Nessuno può decidere al posto tuo. |
| Work that starts on a schedule or an event. | Lavoro che parte a una data programmata o a un evento. |
| Paired devices that can read and decide. | Dispositivi abbinati che possono leggere e decidere. |
| Last run | Ultima esecuzione |
| Last call | Ultima chiamata |
| Schedule | Programmazione |
| Seen | Visto |
| Not scheduled | Non programmata |
| Paired client | Client abbinato |
| ask before git push | chiedi prima di git push |
| format changed files | formatta i file modificati |
| write a checkpoint | scrivi un checkpoint |
| ask before external send | chiedi prima di inviare all’esterno |
| keep writes inside the workdir | tieni le scritture dentro la cartella di lavoro |
| filesystem (read only) | filesystem (sola lettura) |
| issue tracker | gestore delle segnalazioni |
| documentation index | indice della documentazione |
| release notes | note di rilascio |
| planner | pianificatore |
| verifier | verificatore |
| reviewer | revisore |
| doc writer | redattore di documenti |
| Proposes plan versions. It cannot grant an approval. | Propone versioni del piano. Non può concedere un’approvazione. |
| Records checks against a revision. It cannot accept for you. | Registra i controlli su una revisione. Non può accettare al posto tuo. |
| Reviews the evidence. Its verdict is not the same as the process exit. | Esamina le prove. Il suo giudizio non coincide con l’uscita del processo. |
| Drafts documentation. Publishing stays a separate effect. | Prepara la documentazione. Pubblicare resta un effetto a parte. |
| Opens an approval and stops the action. It never pushes by itself. | Apre un’approvazione e ferma l’azione. Non fa mai il push da sola. |
| Runs the project formatter on the files just written. Simulated receipt only. | Esegue il formattatore del progetto sui file appena scritti. Solo ricevuta simulata. |
| Would write a short checkpoint note for a handoff. Disabled, so no checkpoint is promised. | Scriverebbe una breve nota di checkpoint per un passaggio. Disattivo, quindi nessun checkpoint è promesso. |
| Proposal: ask before anything is sent outside this machine. Needs your confirmation to switch on. | Proposta: chiedere prima che qualcosa esca da questa macchina. Serve la tua conferma per attivarla. |
| Denies any path outside the execution workdir. If the hook cannot answer, the action is denied. | Nega ogni percorso fuori dalla cartella di lavoro dell’esecuzione. Se l’hook non sa rispondere, l’azione è negata. |
| Returns the fixture schema. No real filesystem access. | Restituisce lo schema di esempio. Nessun accesso reale ai file. |
| Makes no external requests while it is off. | Non fa richieste esterne finché è spento. |
| Proposed local search over the docs folder. | Ricerca locale proposta sulla cartella dei documenti. |
| Its capability has not been checked, so it cannot be switched on from chat. | La sua capacità non è stata verificata, quindi non si può attivare dalla chat. |
| All projects | Tutti i progetti |
| Local process | Processo locale |
| Any tool | Qualsiasi strumento |
| End of a run | Fine di un’esecuzione |
| conversation | conversazione |
| none yet | ancora nessuno |
| Asked, you approved | Chiesto, hai approvato |
| Asked, waiting for you | Chiesto, in attesa di te |
| Never run | Mai eseguito |
| 2 files formatted | 2 file formattati |
| Checkpoint written | Checkpoint scritto |
| Allowed, inside the workdir | Consentito, dentro la cartella di lavoro |
| What it does | Cosa fa |
| What it is | Cos’è |
| Event | Evento |
| Matches | Corrisponde a |
| Scope | Ambito |
| Runs | Esecuzioni |
| Last outcome | Ultimo esito |
| Calls | Chiamate |
| Tools | Strumenti |
| Read only | Sola lettura |
| Writes, asks first | Scrive, chiede prima |
| Switch off | Spegni |
| Switch on | Accendi |
| See the privileges on Security | Vedi i privilegi in Sicurezza |
| Built in and fail closed: it cannot be switched off. | Integrato e a negazione predefinita: non si può spegnere. |
| Switching this off changes what an execution may do without asking you. It asks you to confirm. | Spegnerlo cambia ciò che un’esecuzione può fare senza chiederti. Ti chiede di confermare. |
| Credentials are never passed to an MCP server by Archeus. | Archeus non passa mai credenziali a un server MCP. |
| An agent proposes or records. It never decides for you: approvals and acceptance stay yours. | Un agente propone o registra. Non decide mai per te: approvazioni e accettazione restano tue. |
| No tool is known yet. | Nessuno strumento è ancora noto. |
| Switch off "ask before git push"? An execution can then do this without asking you. | Spegnere «chiedi prima di git push»? Un’esecuzione potrà farlo senza chiederti. |
| Nightly dependency check | Controllo notturno delle dipendenze |
| Review a pull request when it opens | Rivedi una pull request quando si apre |
| Weekly digest | Riepilogo settimanale |
| Next run | Prossima esecuzione |
| Runs so far | Esecuzioni finora |
| The loop guard tripped; only you can re-enable it. | La guardia anti-ciclo è scattata; solo tu puoi riattivarla. |
| This browser (simulated) | Questo browser (simulato) |
| Phone (simulated) | Telefono (simulato) |
| Old laptop (simulated) | Vecchio portatile (simulato) |
| A paired client can read and decide with its own scope. Revoking it needs a step-up in the real thing. | Un client abbinato può leggere e decidere con il proprio ambito. Revocarlo richiede una conferma rafforzata nella versione reale. |

## Areas dictionary: inspectors

Status: to review. 99 strings.

| English | Italian |
|---|---|
| Relations | Relazioni |
| Overview | Panoramica |
| Route | Percorso |
| Checkpoints | Checkpoint |
| Path | Percorso |
| Item | Elemento |
| Task | Attività |
| Route decision | Decisione di percorso |
| Agent | Agente |
| The time under a station is when the mission first reached it. | L’ora sotto una stazione è quando la missione l’ha raggiunta per la prima volta. |
| Station times are left out: older steps were pruned from the event log. | Gli orari delle stazioni sono omessi: i passi più vecchi sono stati eliminati dal registro eventi. |
| Last change | Ultimo cambiamento |
| Decisions | Decisioni |
| Base revision | Revisione di base |
| Result | Risultato |
| Why it went this way | Perché è andata così |
| Open the decision | Apri la decisione |
| See the route decision | Vedi la decisione di percorso |
| Nothing has been decided yet. | Non è stato ancora deciso nulla. |
| Attempts | Tentativi |
| No attempt yet. | Ancora nessun tentativo. |
| Considered | Valutati |
| Rule | Regola |
| Decided | Deciso |
| Open the task | Apri l’attività |
| Not routed yet. Core routes a task when it is ready to start. | Non ancora instradata. Il Core instrada un’attività quando è pronta a partire. |
| Task key | Chiave dell’attività |
| Latest output | Ultimo output |
| Started | Avviata |
| Last output | Ultimo output |
| Ended because | Terminata perché |
| No checkpoint yet. One is written about every 8 minutes of work, and before a handoff. | Ancora nessun checkpoint. Se ne scrive uno ogni 8 minuti circa di lavoro, e prima di un passaggio. |
| Core keeps a bounded tail for the activity chip, not the whole transcript. | Il Core conserva una coda limitata per l’indicatore di attività, non la trascrizione intera. |
| Policy outcome | Esito della policy |
| Plan policy | Policy del piano |
| External effects | Effetti esterni |
| More than two tasks, so auto-approval does not apply | Più di due attività, quindi l’approvazione automatica non si applica |
| None in the plan | Nessuno nel piano |
| Send the plan back? Core plans again and asks you once more. | Rimandare indietro il piano? Il Core pianifica di nuovo e te lo chiede ancora una volta. |
| Reject this? The mission is cancelled. | Rifiutare? La missione viene annullata. |
| Reject this? The execution ends and the mission is blocked. | Rifiutare? L’esecuzione termina e la missione si blocca. |
| Cancelling ends the mission and stops its runs. This cannot be undone. | Annullare termina la missione e ferma le sue esecuzioni. Non si può annullare. |
| Its paused runs are discarded. This cannot be undone. | Le sue esecuzioni in pausa vengono scartate. Non si può annullare. |
| This cannot be undone. | Non si può annullare. |
| Before it | Prima di essa |
| A new version replaces the one before it; the old version stays in the record. | Una nuova versione sostituisce la precedente; la vecchia resta nel registro. |
| A verifier error is not a failure of the work. Passing a check does not accept the result: you do that on the review. | Un errore del verificatore non è un fallimento del lavoro. Superare un controllo non accetta il risultato: lo fai tu nella revisione. |
| The checks are running. | I controlli sono in corso. |
| No check has run yet. | Nessun controllo è ancora stato eseguito. |
| Verified is not accepted. The verdict is yours. | Verificata non significa accettata. Il giudizio è tuo. |
| An idea is not a commitment. It moves forward only when you say so. | Un’idea non è un impegno. Va avanti solo quando lo dici tu. |
| Park | Parcheggia |
| Bring back | Riporta indietro |
| Understood | Compresa |
| Validated | Convalidata |
| Concept | Concetto |
| Implementing | In realizzazione |
| Completed | Completata |
| Learned | Appresa |
| Source | Fonte |
| You said it | L’hai detto tu |
| Suggested from feedback | Suggerita dai riscontri |
| Archeus will not remember this until you confirm it. | Archeus non lo ricorderà finché non lo confermi. |
| Confirmed: new missions in this project can use it as context. | Confermata: le nuove missioni di questo progetto possono usarla come contesto. |
| Not used as context. | Non usata come contesto. |
| Folder | Cartella |
| Missions | Missioni |
| Confirmed knowledge | Conoscenza confermata |
| Next mission launches | La prossima missione parte con |
| Change the launch settings | Cambia le impostazioni di avvio |
| Plans | Piani |
| Route decisions | Decisioni di percorso |
| Verifications | Verifiche |
| Knowledge it can use | Conoscenza che può usare |
| Account and model | Account e modello |
| Came from | Viene da |
| Task and mission | Attività e missione |
| Runs on | Gira su |
| Asked you | Ti ha chiesto |
| Hook that asked | Hook che ha chiesto |
| Missions that can use it | Missioni che possono usarla |
| Missions from ideas | Missioni nate da idee |
| Pinned. | Fissata. |
| Unpinned. | Rimossa. |
| Under decision | In decisione |
| Showing what this client kept. Decisions are read only until Core is reachable. | Mostra ciò che questo client ha conservato. Le decisioni sono in sola lettura finché il Core non è raggiungibile. |
| This is the last read. It is not live. | È l’ultima lettura. Non è in diretta. |
| Nothing was waiting for a decision when this was kept. | Nessuna decisione era in attesa quando è stato conservato. |
| Read only: decide when Core is back. | Sola lettura: decidi quando il Core è tornato. |
| Read only: accept when Core is back. | Sola lettura: accetta quando il Core è tornato. |
| Blocked or failed | Bloccate o fallite |
| Active | Attive |
| Planning | In pianificazione |
| Done | Fatte |
| Nothing is pinned. Pin a mission or an idea from its details and it stays here. | Niente è fissato. Fissa una missione o un’idea dai suoi dettagli e resta qui. |
| Nothing has changed. | Non è cambiato nulla. |
| Reconnected. | Riconnesso. |
| Marked as seen. | Segnato come visto. |
| Offline: showing what this client kept. | Offline: mostra ciò che questo client ha conservato. |

## Areas dictionary: toasts and reasons

Status: to review. 28 strings.

| English | Italian |
|---|---|
| Hook switched on (simulated). | Hook acceso (simulato). |
| Hook switched off (simulated). | Hook spento (simulato). |
| Agent switched on (simulated). | Agente acceso (simulato). |
| Agent switched off (simulated). | Agente spento (simulato). |
| Connecting (simulated). | Connessione in corso (simulata). |
| Switched off (simulated). | Spento (simulato). |
| Launch setting saved (simulated). | Impostazione di avvio salvata (simulato). |
| Moved up in the failover order. | Spostato su nell’ordine di subentro. |
| Moved down in the failover order. | Spostato giù nell’ordine di subentro. |
| The breaker opened (simulated). | L’interruttore è scattato (simulato). |
| The breaker is closed (simulated). | L’interruttore è chiuso (simulato). |
| Plan sent back (simulated). Core plans again. | Piano rimandato indietro (simulato). Il Core pianifica di nuovo. |
| The hook "ask before git push" is switched off, so the execution did not ask. | L’hook «chiedi prima di git push» è spento, quindi l’esecuzione non ha chiesto. |
| This hook is built in and fail closed: it cannot be switched off. | Questo hook è integrato e nega per impostazione predefinita: non si può spegnere. |
| The breaker is already closed | L’interruttore è già chiuso |
| This harness is not installed | Questo harness non è installato |
| Already at the end | Già in fondo |
| Enable the server first | Prima attiva il server |
| No such hook | Hook inesistente |
| No such server | Server inesistente |
| No such agent | Agente inesistente |
| No such model | Modello inesistente |
| No such project | Progetto inesistente |
| No such harness | Harness inesistente |
| No such rule | Regola inesistente |
| This idea is not on the path | Questa idea non è sul percorso |
| Already offline | Già offline |
| Already connected | Già connesso |

## Areas dictionary: decision notes carried from slice 1

Status: to review. 4 strings.

| English | Italian |
|---|---|
| The serif display font is used for this one line only. | Il carattere serif di visualizzazione è usato solo per questa riga. |
| The core mark sits on the centre of the live map, with its static twin under reduced motion. | Il simbolo del core sta al centro della mappa viva, con il gemello statico quando il movimento è ridotto. |
| Missions grouped by what they wait on, as in V1; the spine shows where each one is (A13). | Missioni raggruppate per ciò che attendono, come nella V1; la spina mostra a che punto è ciascuna (A13). |
| Groups Decide, Review, Unblock; the band is a 12 % tint with the word in ink (B09). No acknowledge or snooze: that needs a Core record. | Gruppi Decidi, Rivedi, Sblocca; la fascia è una tinta al 12 % con la parola in inchiostro (B09). Niente presa visione né rinvio: serve un registro del Core. |

## Areas dictionary: notes

Status: to review. 99 strings.

| English | Italian |
|---|---|
| Isolation (PV-20) is shown as the board records it: designed and fixture tested, physical reach not built, switches off. It is stated, never simulated as working. | L’isolamento (PV-20) è mostrato come lo registra la bacheca: progettato e provato con dati di esempio, raggio d’azione fisico non costruito, interruttori spenti. È dichiarato, mai simulato come funzionante. |
| One breaker per CLI; trip and reset are simulated here; a mission says "cannot start" while it is open. | Un interruttore per CLI; scatto e reimpostazione sono simulati qui; finché è aperto una missione dice «non può avviare». |
| One breaker per CLI. While it is open a mission shows "cannot start" and dispatch waits; Reset needs a step-up in the real thing. | Un interruttore per CLI. Finché è aperto una missione mostra «non può avviare» e l’avvio attende; la reimpostazione richiede una conferma rafforzata nella versione reale. |
| Eight boundaries, each with its policy layer and its physical layer named apart. Neither stands in for the other. | Otto confini, ciascuno con il livello di policy e il livello fisico indicati a parte. Nessuno sostituisce l’altro. |
| Health is read from records, one live derivation (P21 D12). Each check has a cause and a fix when it is not OK. | Lo stato di salute è letto dai registri, una sola derivazione in diretta (P21 D12). Ogni controllo ha una causa e una soluzione quando non è OK. |
| Health is read from records: one live derivation, a cause and a fix when it is not OK, and unknown where nothing was read. | Lo stato di salute è letto dai registri: una sola derivazione in diretta, una causa e una soluzione quando non è OK, e sconosciuto dove non si è letto nulla. |
| Usage: a ring is what is left and empties as it is used; the tick is your 20% line. "20% weekly usage" is read here as 20% left (owner to confirm). Unknown stays unknown. | Utilizzo: un anello è ciò che resta e si svuota man mano che si usa; il segno è la tua soglia del 20%. «20% di utilizzo settimanale» è letto qui come 20% rimasto (da confermare con il proprietario). Sconosciuto resta sconosciuto. |
| Accounts and models: three accounts in a failover order, four models with one default, per-project launch settings. No token is shown or handled. | Account e modelli: tre account in ordine di subentro, quattro modelli con uno predefinito, impostazioni di avvio per progetto. Nessun token è mostrato o gestito. |
| Accounts and models: four models across two harnesses, one default; a project can override it in its launch settings. | Account e modelli: quattro modelli su due harness, uno predefinito; un progetto può cambiarlo nelle sue impostazioni di avvio. |
| Hooks, MCP servers and agents managers: status, last run, enable and disable, and a details sheet for each. Automations and clients are the other Control lists. | Gestori di hook, server MCP e agenti: stato, ultima esecuzione, attiva e disattiva, e una scheda di dettaglio per ciascuno. Automazioni e client sono le altre liste di Controllo. |
| Hooks are listed with status and last run; enable and disable go through a confirm when they guard something. | Gli hook sono elencati con stato e ultima esecuzione; attivare e disattivare passa da una conferma quando proteggono qualcosa. |
| MCP servers: status, last call, enable and disable. A server whose capability has not been checked cannot be switched on from chat. | Server MCP: stato, ultima chiamata, attiva e disattiva. Un server la cui capacità non è stata verificata non si può attivare dalla chat. |
| Agents are listed with the model tier they use, what they are doing now and when they last ran. | Gli agenti sono elencati con il livello di modello che usano, cosa stanno facendo ora e quando sono stati eseguiti l’ultima volta. |
| Relations lists what this thing is connected to; each row opens its own details. | Le relazioni elencano a cosa è collegata questa cosa; ogni riga apre i propri dettagli. |
| Time at each station on the inspector spine; omitted when events are pruned. | Il tempo a ogni stazione sulla spina dell’ispettore; omesso quando gli eventi sono stati eliminati. |
| Why lists each decision with its reason, in plain words, and who made it: Core by policy, or you on a card. | Il Perché elenca ogni decisione con la sua ragione, a parole semplici, e chi l’ha presa: il Core per policy, o tu su una scheda. |
| The mission trace shows attempts, not a transcript: each execution is one attempt, and failures stay visible. | La traccia della missione mostra i tentativi, non una trascrizione: ogni esecuzione è un tentativo, e i fallimenti restano visibili. |
| A route decision names every candidate and why it was chosen, passed over or not eligible. Nothing is picked silently. | Una decisione di percorso nomina ogni candidato e perché è stato scelto, scartato o non idoneo. Niente è scelto in silenzio. |
| Execution inspector: Output, Checkpoints, Facts. The private reasoning and tool transcript are not recorded (see Replay, Not recorded). | Ispettore dell’esecuzione: Output, Checkpoint, Fatti. Il ragionamento privato e la trascrizione degli strumenti non sono registrati (vedi Replay, Non registrato). |
| Policy shows which rule made this a decision for you, so a card is never unexplained. | La policy mostra quale regola ha reso questa una decisione per te, così una scheda non resta mai senza spiegazione. |
| On a phone a decision takes two steps: choose, then confirm. Reject always asks twice. | Su un telefono una decisione ha due passi: scegli, poi conferma. Rifiutare chiede sempre due volte. |
| The idea path runs Captured to Learned; Parked and Discarded sit beside it. | Il percorso dell’idea va da Catturata ad Appresa; Parcheggiata e Scartata stanno accanto. |
| Every idea shows where it is on the path from Captured to Learned. An idea is not a commitment. | Ogni idea mostra a che punto è sul percorso da Catturata ad Appresa. Un’idea non è un impegno. |
| The digest groups what changed since your cursor; marking it seen moves the cursor. It reads the event log; nothing is counted twice. | Il riepilogo raggruppa ciò che è cambiato dal tuo segno; segnarlo come visto sposta il segno. Legge il registro eventi; niente è contato due volte. |
| Offline Now: kept missions with their spine drawn outlined, the time it was last seen, and Decide rows read only (D11). | Adesso offline: missioni conservate con la spina disegnata a contorno, l’ora dell’ultimo accesso e le righe Decidi in sola lettura (D11). |
| Began to understand it | Ha iniziato a capirla |
| Understood the request | Ha capito la richiesta |
| Asked you a question | Ti ha fatto una domanda |
| Gathered the context | Ha raccolto il contesto |
| Drafted a plan | Ha preparato un piano |
| Plan approved by policy | Piano approvato dalla policy |
| Sent the plan to you | Ti ha inviato il piano |
| Plan approved | Piano approvato |
| Plan rejected | Piano rifiutato |
| Plan sent back | Piano rimandato indietro |
| Started the executions | Ha avviato le esecuzioni |
| Moved to verification | Passata alla verifica |
| Verified | Verificata |
| Replanning after a failed check | Ripianifica dopo un controllo fallito |
| Accepted | Accettata |
| Resumed | Ripresa |
| Unblocked | Sbloccata |
| Blocked: replan budget used | Bloccata: budget di ripianificazione esaurito |
| Replanning after an error | Ripianifica dopo un errore |
| Started again | Riavviata |
| An execution went quiet | Un’esecuzione è rimasta in silenzio |
| Adopted the execution again | Ha adottato di nuovo l’esecuzione |
| Asked you to decide | Ti ha chiesto di decidere |
| The mission was created from conversation, so Core starts by reading what was asked. | La missione è nata da una conversazione, quindi il Core comincia leggendo ciò che è stato chiesto. |
| The request was clear enough to go on without asking you. | La richiesta era abbastanza chiara da proseguire senza chiederti nulla. |
| Confirmed project knowledge and the recent changes were collected into the context package. | La conoscenza confermata del progetto e le modifiche recenti sono state raccolte nel pacchetto di contesto. |
| Reasoning finished with a plan of tasks. | Il ragionamento si è concluso con un piano di attività. |
| The plan is low risk: it touches only files in the workdir and runs the project checks, so policy approved it without asking you. | Il piano ha rischio basso: tocca solo file nella cartella di lavoro ed esegue i controlli del progetto, quindi la policy l’ha approvato senza chiederti nulla. |
| Policy needs a person on this plan: it has more than two tasks, or it changes behaviour other work relies on. | La policy vuole una persona su questo piano: ha più di due attività, oppure cambia un comportamento su cui si appoggia altro lavoro. |
| The decision was made on the card. | La decisione è stata presa sulla scheda. |
| A rejected plan cancels the mission. | Un piano rifiutato annulla la missione. |
| Changes were requested, so Core plans again. | Sono state chieste modifiche, quindi il Core pianifica di nuovo. |
| The plan was approved and no spawn breaker was open, so Core dispatched the tasks. | Il piano era approvato e nessun interruttore di avvio era aperto, quindi il Core ha avviato le attività. |
| Every task finished its run, so the checks start on the recorded base revision. | Ogni attività ha finito la sua esecuzione, quindi i controlli partono sulla revisione di base registrata. |
| Every check passed. A person still has to accept the result. | Ogni controllo è stato superato. Una persona deve ancora accettare il risultato. |
| You reviewed the verified result and accepted it. | Hai esaminato il risultato verificato e l’hai accettato. |
| The review asked for changes, so Core plans again. | La revisione ha chiesto modifiche, quindi il Core pianifica di nuovo. |
| The runs stopped at a safe boundary; nothing is lost. | Le esecuzioni si sono fermate a un confine sicuro; nulla è andato perso. |
| The paused runs start again from their last boundary. | Le esecuzioni in pausa ripartono dall’ultimo confine. |
| The question was answered, so the mission goes on from where it was held. | La domanda ha avuto risposta, quindi la missione prosegue da dove era ferma. |
| A failed mission can be planned again within the replan budget. | Una missione fallita può essere pianificata di nuovo entro il budget di ripianificazione. |
| The mission was replanned three times; a person has to decide what to do. | La missione è stata ripianificata tre volte; una persona deve decidere cosa fare. |
| An execution ended with an error. A retry is allowed inside the replan budget. | Un’esecuzione è finita con un errore. Un nuovo tentativo è consentito entro il budget di ripianificazione. |
| Cancelling ends the mission and stops its runs. | Annullare termina la missione e ferma le sue esecuzioni. |
| Core started the held tasks again. | Il Core ha riavviato le attività ferme. |
| No output heartbeat for two minutes. Core reconciles instead of guessing that it died. | Nessun segnale di output per due minuti. Il Core riconcilia invece di supporre che sia morta. |
| The process was found again, so Core adopted it instead of starting a second one. | Il processo è stato ritrovato, quindi il Core lo ha adottato invece di avviarne un secondo. |
| Read the task and the project notes | Ha letto l’attività e le note del progetto |
| Ran the checks: 3 failing | Ha eseguito i controlli: 3 falliscono |
| Found the cause in two helpers | Ha trovato la causa in due funzioni di supporto |
| Edited the first helper | Ha modificato la prima funzione di supporto |
| Re-ran the checks: 1 failing | Ha rieseguito i controlli: 1 fallisce |
| Edited the second helper | Ha modificato la seconda funzione di supporto |
| Wrote a test for the edge case | Ha scritto un test per il caso limite |
| Re-ran the checks: all passing | Ha rieseguito i controlli: tutti superati |
| Summarised the change for verification | Ha riassunto la modifica per la verifica |
| Checked the diff against the plan | Ha confrontato le differenze con il piano |
| Wrote the commit message | Ha scritto il messaggio di commit |
| Wrote the notes and the list of changed files | Ha scritto le note e l’elenco dei file modificati |
| Saved the plan position and 2 changed files | Ha salvato la posizione nel piano e 2 file modificati |
| First eligible by priority; its state is available. | Primo idoneo per priorità; il suo stato è disponibile. |
| Lower priority, and Claude Code, work was available. | Priorità più bassa, e Claude Code, work era disponibile. |
| Tu | Core |
| te | Core |
|  a ora |  alle  |
| finestra di 5 ore | settimana |
|  sono |  è |
| sua settimana | sua finestra di 5 ore |
| request changes | chiedi modifiche |
| switch off | spegni |
| Approval mode | Modalità di approvazione |
| attivato | disattivato |
| MCP server | il server MCP |
|  + m[1] +  |  + tr2(m[2])], [/^(d+) needs? you$/, (m) => m[1] + (m[1] ===  |

## Finishing slice (keyboard help, counters, control strip, No Undo, Dismiss)

Status: to review. 25 strings.

| English | Italian |
|---|---|
| Enter | Invio |
| Space | Spazio |
| Dismiss | Chiudi |
| No Undo. | Non si annulla. |
| Decision cannot be changed. | La decisione non si può cambiare. |
| Counts | Conteggi |
| needs you | ti servono |
| running | in corso |
| stopped | fermi |
| verifying | in verifica |
| Not stopped: accepts new work. | Non fermato: accetta nuovo lavoro. |
| Stop every running mission and block new dispatch until you re-arm? Each mission then waits for you. | Fermare ogni missione in corso e bloccare i nuovi avvii finché non riarmi? Ogni missione poi aspetta te. |
| Keyboard shortcuts | Scorciatoie da tastiera |
| Keyboard shortcuts (?) | Scorciatoie da tastiera (?) |
| Next and previous row in a list | Riga successiva e precedente in un elenco |
| Open the focused row, or do the primary action of the focused card | Apre la riga selezionata, o fa l’azione principale della scheda selezionata |
| The same as Enter on a row | Come Invio su una riga |
| Close the open help, menu, question or details sheet | Chiude la guida, il menu, la domanda o il pannello dei dettagli aperto |
| Show or hide this list | Mostra o nasconde questo elenco |
| Tab and Shift+Tab | Tab e Maiusc+Tab |
| Move between controls | Passa da un controllo all’altro |
| / in the chat bar | / nella barra della chat |
| Open the command list; Up, Down, Tab, Enter and Esc work inside it | Apre l’elenco dei comandi; dentro funzionano Su, Giù, Tab, Invio e Esc |
| Focus order: toolbar, navigation, page, chat bar, bottom bar, then the details sheet, which takes focus when it opens and gives it back when it closes. | Ordine del focus: barra degli strumenti, navigazione, pagina, barra della chat, barra in basso, poi il pannello dei dettagli, che prende il focus quando si apre e lo restituisce quando si chiude. |
| The terminal view has its own keys; press ? there. | La vista terminale ha i suoi tasti; premi ? lì. |

## Slash commands: Italian aliases, argument labels and descriptions

Status: to review. 61 strings.

| English | Italian |
|---|---|
| READ | CREATE |
| Command (optional) | Comando (facoltativo) |
| List the commands, or the usage of one | Elenca i comandi, o come si usa uno |
| Core, emergency state, running and waiting work | Core, stato di emergenza, lavoro in corso e in attesa |
| Account (optional) | Account (facoltativo) |
| Usage per account. Unknown until the usage read exists | Utilizzo per account. Sconosciuto finché la lettura non esiste |
| The projects and their open missions | I progetti e le loro missioni aperte |
| Project (optional) | Progetto (facoltativo) |
| What waits for you. Nothing is decided here | Cosa aspetta te. Qui non si decide nulla |
| What changed since you left | Cosa è cambiato da quando sei andato via |
| Open the plan of a mission | Apri il piano di una missione |
| Decision id (for example rd-1) | Id della decisione (per esempio rd-1) |
| Explain one route decision | Spiega una decisione di instradamento |
| Text to find | Testo da cercare |
| Search projects, missions and ideas | Cerca progetti, missioni e idee |
| Open the trace of a mission | Apri la traccia di una missione |
| Mission (optional) | Missione (facoltativa) |
| Open the Replay at a mission, or the latest | Apri il Replay di una missione, o dell'ultima |
| Name or id | Nome o id |
| Open a project or a mission | Apri un progetto o una missione |
| Move the map to a project | Sposta la mappa su un progetto |
| Hide earlier messages on this screen. History is kept | Nascondi i messaggi precedenti su questo schermo. La cronologia resta |
| system | light |
| system, light, dark or contrast | system, light, dark o contrast |
| Set the colour theme on this device | Imposta il tema dei colori su questo dispositivo |
| full | quiet |
| full, quiet or reduced | full, quiet o reduced |
| Set motion on this device | Imposta il movimento su questo dispositivo |
| Mission in one line | Missione in una riga |
| Create a mission. A Start card asks next | Crea una missione. Poi una scheda chiede l'avvio |
| Idea in one line | Idea in una riga |
| Capture an idea. It is not a commitment | Cattura un'idea. Non è un impegno |
| Save feedback as a candidate | Salva un feedback come candidato |
| What to remember | Cosa ricordare |
| Remember a fact, after a card names where | Ricorda un fatto, dopo una scheda che dice dove |
| Message | Messaggio |
| Send the text as a plain message | Invia il testo come messaggio semplice |
| Question | Domanda |
| Ask in the general thread, outside project memory | Chiedi nel thread generale, fuori dalla memoria dei progetti |
| Propose starting a mission. A card asks first | Proponi di avviare una missione. Prima chiede una scheda |
| Propose a stop. Two-step confirm | Proponi un arresto. Conferma in due passi |
| Propose an emergency stop. Two-step confirm | Proponi un arresto d'emergenza. Conferma in due passi |
| Propose a pause. A card asks first | Proponi una pausa. Prima chiede una scheda |
| Propose a resume. A card asks first | Proponi di riprendere. Prima chiede una scheda |
| Propose a cancel. Cannot be undone, two-step | Proponi di annullare. Non si può disfare, due passi |
| Open the review. The command decides nothing | Apri la revisione. Il comando non decide nulla |
| Open the approval card. The command decides nothing | Apri la scheda di approvazione. Il comando non decide nulla |
| Open the approval card to reject. Decides nothing | Apri la scheda per rifiutare. Non decide nulla |
| Propose a change to an account | Proponi una modifica a un account |
| Needs an admin device. Not on this device. | Serve un dispositivo amministratore. Non su questo dispositivo. |
| /project is not available from chat. Create projects in Control on an admin device. | /project non è disponibile dalla chat. Crea i progetti in Controllo su un dispositivo amministratore. |
| /delete is not available from chat. Nothing is deleted without a card; open Work. | /delete non è disponibile dalla chat. Niente si elimina senza una scheda; apri Lavoro. |
| /archive is not available from chat. Open Work. | /archive non è disponibile dalla chat. Apri Lavoro. |
| /run is not available from chat. A command, shell or script never runs from here; open Work. | /run non è disponibile dalla chat. Da qui non gira mai un comando, una shell o uno script; apri Lavoro. |
| /exec is not available from chat. Nothing runs from here; open Work. | /exec non è disponibile dalla chat. Da qui non gira nulla; apri Lavoro. |
| /shell is not available from chat. Nothing runs from here. | /shell non è disponibile dalla chat. Da qui non gira nulla. |
| /policy is not available from chat. Policy is changed in Control by an owner device. | /policy non è disponibile dalla chat. La policy si cambia in Controllo da un dispositivo del proprietario. |
| /login is not available from chat. Archeus never handles credentials. | /login non è disponibile dalla chat. Archeus non gestisce mai credenziali. |
| /token is not available from chat. Archeus never handles tokens. | /token non è disponibile dalla chat. Archeus non gestisce mai token. |
| /pair is not available from chat. Pairing a device is done in Control. | /pair non è disponibile dalla chat. L'abbinamento di un dispositivo si fa in Controllo. |
| /push is not available from chat. Nothing leaves Archeus from here. | /push non è disponibile dalla chat. Da qui non esce nulla da Archeus. |

## Chat: replies, cards and refusals

Status: to review. 68 strings.

| English | Italian |
|---|---|
| Core elected the work account for “Fix date test” because the personal account was near its ceiling. | Il Core ha scelto l'account di lavoro per “Fix date test” perché quello personale era vicino al limite. |
| Core elected Sonnet 5.5 for the plan of “Search provenance”: the plan needs the large tier. | Il Core ha scelto Sonnet 5.5 per il piano di “Search provenance”: il piano richiede il livello grande. |
| Core held the dispatch of “Voice notes prototype” because you paused it. A pause is yours to release. | Il Core ha trattenuto l'avvio di “Voice notes prototype” perché l'hai messa in pausa. Una pausa la rilasci tu. |
| A Replay shows what was intended, what you authorized, what was durably recorded, what may have taken effect and where the state is uncertain. Recovery proposes new work; it never claims an external effect can be undone. | Un Replay mostra cosa era previsto, cosa hai autorizzato, cosa è stato registrato in modo durevole, cosa può aver avuto effetto e dove lo stato è incerto. Il recupero propone nuovo lavoro; non afferma mai che un effetto esterno si possa annullare. |
| An approval is bound to one action and one version. Changing the plan or the target makes an earlier confirmation stale. A bare “yes” never approves. | Un'approvazione è legata a una sola azione e a una sola versione. Cambiare il piano o il bersaglio rende vecchia la conferma precedente. Un semplice “sì” non approva mai. |
| Pause halts work at a safe boundary and can be resumed. Stop ends the running execution and cannot be undone from chat. Emergency stop pauses everything that runs. | La pausa ferma il lavoro a un confine sicuro e si può riprendere. L'arresto termina l'esecuzione in corso e non si disfa dalla chat. L'arresto d'emergenza mette in pausa tutto ciò che gira. |
| A project holds missions; a mission is one piece of work with a plan, tasks and runs; an idea is a note that is not a commitment. | Un progetto contiene missioni; una missione è un lavoro con un piano, attività ed esecuzioni; un'idea è una nota che non è un impegno. |
| This is not about a project, so it stays in the general thread. This prototype answers with fixed text; a real build answers through the official CLI on the account Core selects. Nothing here reaches project memory unless you remember it. | Non riguarda un progetto, quindi resta nel thread generale. Questo prototipo risponde con testo fisso; una versione reale risponde tramite la CLI ufficiale sull'account scelto dal Core. Niente qui entra nella memoria dei progetti se non lo ricordi tu. |
| project | progetto |
| No project or mission named “{q}”. Closest: {list}. | Nessun progetto o missione di nome “{q}”. Più simili: {list}. |
| More than one matches “{q}”. Pick one; nothing was sent. | Più di una corrisponde a “{q}”. Scegline una; non è stato inviato nulla. |
| Based on available Core context. | In base al contesto disponibile del Core. |
| The commands, by class. READ and NAVIGATE answer, CREATE writes one record, PROPOSE only makes a card you confirm. | I comandi, per classe. READ e NAVIGATE rispondono, CREATE scrive un record, PROPOSE crea solo una scheda che confermi tu. |
| Usage is Unknown. The read is not built yet (T-154); Archeus shows no number it cannot source. | L'utilizzo è Sconosciuto. La lettura non esiste ancora (T-154); Archeus non mostra numeri che non può documentare. |
| COMPLETED | CANCELLED |
| {n} wait for you. Nothing is decided here; each row opens its card. | {n} aspettano te. Qui non si decide nulla; ogni riga apre la sua scheda. |
| Nothing waits for you. | Niente aspetta te. |
| Since you left (the last simulated hour). | Da quando sei andato via (l'ultima ora simulata). |
| {n} found for “{q}”. A row opens the object. | {n} trovati per “{q}”. Una riga apre l'oggetto. |
| Nothing found for “{q}”. | Niente trovato per “{q}”. |
| No route decision “{q}”. Closest: rd-1, rd-2, rd-3. | Nessuna decisione di instradamento “{q}”. Più vicine: rd-1, rd-2, rd-3. |
| The plan of “{t}”. | Il piano di “{t}”. |
| Opening the Replay of “{t}”, the latest. | Apro il Replay di “{t}”, l'ultima. |
| mission | project |
| Focusing the map on {t}. | Porto la mappa su {t}. |
| Opening the Replay of “{t}”. | Apro il Replay di “{t}”. |
| Opening the trace of “{t}”. | Apro la traccia di “{t}”. |
| Opening “{t}”. | Apro “{t}”. |
| Theme set to {v} on this device. | Tema impostato su {v} su questo dispositivo. |
| Motion set to {v} on this device. The facts stay the same. | Movimento impostato su {v} su questo dispositivo. I fatti restano gli stessi. |
| No project “{q}”. Nothing was created. | Nessun progetto “{q}”. Non è stato creato nulla. |
| Created “{t}” in {p}. Not started. Starting it needs your approval. | Creata “{t}” in {p}. Non avviata. Per avviarla serve la tua approvazione. |
| Idea captured. It is not a commitment. | Idea catturata. Non è un impegno. |
| Feedback saved as a candidate. | Feedback salvato come candidato. |
| Nothing is written until you confirm where to remember it. | Non si scrive nulla finché non confermi dove ricordarlo. |
| EXECUTING | running |
| PAUSED | paused |
| The emergency stop is already engaged. Nothing new starts until you re-arm it in Settings; that needs a step-up and is not done from chat. | L'arresto d'emergenza è già attivo. Non parte nulla di nuovo finché non lo riarmi in Impostazioni; serve una conferma rafforzata e non si fa dalla chat. |
| Nothing is running, so there is nothing to pause. | Niente è in esecuzione, quindi non c'è nulla da mettere in pausa. |
| Emergency stop is a proposal. Nothing has happened. | L'arresto d'emergenza è una proposta. Non è successo nulla. |
| Pausing everything that runs is a proposal. Nothing has happened. | Mettere in pausa tutto ciò che gira è una proposta. Non è successo nulla. |
| Approval {id} is open for “{t}”. The command decides nothing; only the card’s own button does. | L’approvazione {id} è aperta per “{t}”. Il comando non decide nulla; decide solo il pulsante della scheda. |
| Approval {id} is already {w}. | L’approvazione {id} è già {w}. |
| “{t}” waits for your review. The command decides nothing. | “{t}” aspetta la tua revisione. Il comando non decide nulla. |
| “{t}” has no review waiting. | “{t}” non ha revisioni in attesa. |
| A decision waits on “{t}”. The command decides nothing; only the card’s own button does. | Una decisione aspetta su “{t}”. Il comando non decide nulla; decide solo il pulsante della scheda. |
| “{t}” has no decision waiting. | “{t}” non ha decisioni in attesa. |
| Starting “{t}” is a proposal. Nothing has started. | Avviare “{t}” è una proposta. Non è partito nulla. |
| “{t}” is {w}, so /start does not apply. | “{t}” è {w}, quindi /start non si applica. |
| Cancelling “{t}” is a proposal and cannot be undone. Nothing has happened. | Annullare “{t}” è una proposta e non si può disfare. Non è successo nulla. |
| “{t}” is {w} and cannot be cancelled here. | “{t}” è {w} e non si può annullare da qui. |
| “{t}” is {w}, so /{n} does not apply. | “{t}” è {w}, quindi /{n} non si applica. |
| {v} “{t}” is a proposal. Nothing has happened. | “{t}”: {v} è una proposta. Non è successo nulla. |
| A bare word never approves. Open the decision card; only its own button decides, bound to its hash. | Una parola da sola non approva mai. Apri la scheda della decisione; decide solo il suo pulsante, legato al suo hash. |
| I can’t do that from chat; open Work. Deleting or archiving needs a card. | Non posso farlo dalla chat; apri Lavoro. Eliminare o archiviare richiede una scheda. |
| I can’t do that from chat; open Work. A command, shell or script never runs from here. | Non posso farlo dalla chat; apri Lavoro. Un comando, una shell o uno script non girano mai da qui. |
| I can’t do that from chat; open Work. Policy, limits and credentials are never changed from here. | Non posso farlo dalla chat; apri Lavoro. Policy, limiti e credenziali non si cambiano mai da qui. |
| SIMULATED · Project “{t}” created in this demo. Core chat creation is not connected. It is a record only; folders, clones and access are proposals. | SIMULATO · Progetto “{t}” creato in questa demo. La creazione da chat nel Core non è collegata. È solo un record; cartelle, cloni e accessi sono proposte. |
| Mission created. Starting it needs your approval. | Missione creata. Per avviarla serve la tua approvazione. |
| Answer this, or create work? | Rispondo a questo, o creo del lavoro? |
| I heard you. Name the project, mission, idea or proposal you want. Nothing was created or executed. | Ti ho sentito. Dimmi il progetto, la missione, l'idea o la proposta che vuoi. Non è stato creato né eseguito nulla. |
| Sent as ordinary text: {t}. No slash handler ran. | Inviato come testo normale: {t}. Nessun comando slash è partito. |
| Write a message first. | Scrivi prima un messaggio. |
| This looks like a secret, so it was not sent. | Sembra un segreto, quindi non è stato inviato. |
| Unknown command /{n}. Type / for the list, or //{n} to send the text as a message. | Comando /{n} sconosciuto. Scrivi / per l'elenco, oppure //{n} per inviare il testo come messaggio. |
| Nothing to do. | Niente da fare. |
| stop | estop |
| Where should this be remembered? Nothing is written until you confirm. | Dove va ricordato? Non si scrive nulla finché non confermi. |

## Chat: card text

Status: to review. 102 strings.

| English | Italian |
|---|---|
| This is a simulated decision: nothing is run, sent or spent. | Decisione simulata: nulla viene eseguito, inviato o speso. |
| READ | LETTURA |
| CREATE | CREA |
| PROPOSE | PROPONI |
| NAVIGATE | NAVIGA |
| General · not project memory | Generale · non è memoria di progetto |
| Work · {p} | Lavoro · {p} |
| Usage | Uso |
| Commands by class | Comandi per classe |
| Type / for the list with descriptions. //text sends a slash as plain text. READ and NAVIGATE are not recorded. | Scrivi / per l'elenco con le descrizioni. //testo invia uno slash come testo semplice. READ e NAVIGATE non vengono registrati. |
| Status, as of {t} | Stato, alle {t} |
| Reachable (simulated) | Raggiungibile (simulato) |
| Emergency stop | Arresto di emergenza |
| Not engaged | Non attivo |
| Running | In corso |
| Waiting for you | Aspettano te |
| Stopped | Fermi |
| Accepting new work | Accetta nuovo lavoro |
| Unknown is shown when the status read does not carry the field, never a guess. | Sconosciuto appare quando la lettura non porta il campo, mai un'ipotesi. |
| Unknown is never shown as 0. Numbers come only from the existing usage reader, once T-154 exists. No token is ever shown. | Sconosciuto non è mai mostrato come 0. I numeri verranno solo dal lettore di utilizzo esistente, quando esisterà T-154. Nessun token è mai mostrato. |
| +{n} more | +{n} altri |
| Route decision {id} | Decisione di instradamento {id} |
| Served model and billed cost | Modello servito e costo fatturato |
| Selected by Core | Scelto dal Core |
| Plan v{v} · {s} | Piano v{v} · {s} |
| No plan yet | Ancora nessun piano |
| The plan is made after the mission starts. | Il piano si fa dopo l'avvio della missione. |
| Open plan | Apri il piano |
| Created · {w} | Creato · {w} |
| Show | Mostra |
| “{t}” started. Planning is under way; the plan waits for your approval before anything executes. | “{t}” avviata. La pianificazione è in corso; il piano aspetta la tua approvazione prima che si esegua qualcosa. |
| Kept as mission | Tenuta come missione |
| “{t}” is kept. Not started. Archeus will not ask again. | “{t}” è tenuta. Non avviata. Archeus non lo chiederà di nuovo. |
| No longer applies | Non si applica più |
| Proposed · nothing has started | Proposta · non è partito nulla |
| Start and plan “{t}”? | Avviare e pianificare “{t}”? |
| Starting “{t}” needs your approval | Avviare “{t}” richiede la tua approvazione |
| Start “{t}” in {p} and ask the planner for a plan. | Avviare “{t}” in {p} e chiedere un piano al pianificatore. |
| You created it from chat. Chat creation never starts work by itself. | L'hai creata dalla chat. La creazione da chat non avvia mai il lavoro da sola. |
| Core consequence | Conseguenza per il Core |
| Planning runs on an account Core selects. Account and cost: Unknown. The plan then waits for your approval; nothing executes before it. | La pianificazione gira su un account scelto dal Core. Account e costo: Sconosciuti. Il piano poi aspetta la tua approvazione; nulla si esegue prima. |
| Review it first, or keep it as a mission. Keeping leaves it idle and asks no more. | Rivedila prima, oppure tienila come missione. Tenerla la lascia ferma e non chiede altro. |
| Start and plan | Avvia e pianifica |
| Review proposal | Rivedi la proposta |
| Keep as mission | Tieni come missione |
| (nothing is running now) | (niente in esecuzione ora) |
| Stop | Ferma |
| Ends its running execution. Work already recorded stays recorded. This cannot be undone from chat. | Termina la sua esecuzione in corso. Il lavoro già registrato resta registrato. Dalla chat non si può disfare. |
| Emergency stop | Arresto d'emergenza |
| Stops every running execution, not only their scheduling, and blocks new dispatch until you re-arm in Settings (a step-up). This cannot be undone from chat. | Ferma ogni esecuzione in corso, non solo la loro pianificazione, e blocca ogni nuovo avvio finché non riarmi in Impostazioni (conferma rafforzata). Dalla chat non si può disfare. |
| Cancel | Annulla |
| Cancels the mission. It cannot undo effects an earlier run may have had. | Annulla la missione. Non può disfare gli effetti che un'esecuzione precedente può aver avuto. |
| Halts the work at a safe boundary. You can resume it. | Ferma il lavoro a un confine sicuro. Puoi riprenderlo. |
| A new dispatch may spend usage. Account and cost: Unknown. | Un nuovo avvio può consumare quota. Account e costo: Sconosciuti. |
| Done for {n}: {t}. | Fatto per {n}: {t}. |
| Dismissed | Scartata |
| Nothing was done. | Non è stato fatto nulla. |
| Proposed · nothing has happened | Proposta · non è successo nulla |
| Confirm: {a} {t} now? | Conferma: {a} {t} adesso? |
| Step 2 of 2 | Passo 2 di 2 |
| Step 1 of 2 | Passo 1 di 2 |
| Yes, {a} | Sì, {a} |
| {a} mission | {a} missione |
| This decision no longer exists. | Questa decisione non esiste più. |
| No longer waiting | Non è più in attesa |
| Decided by {w}. {s} | Deciso da {w}. {s} |
| you | te |
| Core | il Core |
| Bound to | Legata a |
| action hash {h} · plan version {v} | hash dell'azione {h} · versione del piano {v} |
| Step-up needed: confirm it is you before this is {w}. (Simulated step-up.) | Serve la conferma d'identità: conferma che sei tu prima che sia {w}. (Conferma simulata.) |
| approved | approvata |
| rejected | rifiutata |
| Only this card’s own button decides. A message or a bare “yes” never does. | Decide solo il pulsante di questa scheda. Un messaggio o un semplice “sì” non decide mai. |
| Confirm approval | Conferma l'approvazione |
| Confirm rejection | Conferma il rifiuto |
| all projects | tutti i progetti |
| Remembered | Ricordato |
| Remembered for {s}: “{t}” (item {i}). | Ricordato per {s}: “{t}” (voce {i}). |
| Nothing was written. | Non è stato scritto nulla. |
| Remember in | Ricorda in |
| Choose where… | Scegli dove… |
| Remember in {s}? | Ricordare in {s}? |
| Remember in… | Ricorda in… |
| Nothing is written until you confirm. There is no silent global memory. Conversation retention: Unknown. | Non si scrive nulla finché non confermi. Non esiste memoria globale implicita. Conservazione della conversazione: Sconosciuta. |
| No star, no link, no activity for a general answer. “Not project memory” does not mean “not stored”. | Nessuna stella, nessun collegamento, nessuna attività per una risposta generale. “Non è memoria di progetto” non vuol dire “non archiviato”. |
| Account selected by Core · Usage: Unknown · Conversation retention: Unknown | Account scelto dal Core · Utilizzo: Sconosciuto · Conservazione della conversazione: Sconosciuta |
| Answered in General. | Risposto in Generale. |
| Sent as work. | Inviato come lavoro. |
| Nothing was created and nothing was sent anywhere yet. | Non è stato creato nulla e non è stato inviato nulla. |
| Answer in General | Rispondi in Generale |
| Create work | Crea lavoro |
| Pick one. Nothing was sent. | Scegline una. Non è stato inviato nulla. |
| Picked. | Scelta. |
| Not from chat | Non dalla chat |
| Open Attention | Apri Attenzione |
| Open Security | Apri Sicurezza |
| Open Work | Apri Lavoro |
| Submitted. | Inviato. |
| Not sent. Send again? | Non inviato. Rimandare? |
| Send again | Rimanda |
| Local view: READ and NAVIGATE answers are not recorded. | Vista locale: le risposte READ e NAVIGATE non vengono registrate. |

## Chat: page, dock and phone sheet

Status: to review. 56 strings.

| English | Italian |
|---|---|
| Not done: {r} | Non fatto: {r} |
| Earlier messages hidden on this screen. History kept. | Messaggi precedenti nascosti su questo schermo. La cronologia resta. |
| Ask a question, capture an idea, or describe work. | Fai una domanda, cattura un'idea o descrivi un lavoro. |
| New reply | Nuova risposta |
| Destination: Command · /{n} · {c} | Destinazione: Comando · /{n} · {c} |
| Destination: General · not project memory. Nothing here is saved to a project. | Destinazione: Generale · non è memoria di progetto. Qui non si salva nulla in un progetto. |
| Destination: Work · {p}. Replies and records stay in this project. | Destinazione: Lavoro · {p}. Risposte e record restano in questo progetto. |
| Tell Archeus what to do… | Dì ad Archeus cosa fare… |
| Destination | Destinazione |
| Stop: propose an emergency stop | Ferma: proponi un arresto d'emergenza |
| mission | missione |
| Enter sends, Esc cancels | Invio invia, Esc annulla |
| {n} commands. {c}: {d}, {k} | {n} comandi. {c}: {d}, {k} |
| {n} more commands | {n} altri comandi |
| You sent this {n} s ago. Send again? | Hai inviato questo {n} s fa. Rimandare? |
| /status | work |
| /needs | work |
| /mission Audit export labels @Notes | work |
| /stop fix date | work |
| /estop | work |
| /approve search | work |
| /remember Reports use UTC | work |
| Create a mission to export backups and start it | work |
| Explain a checkpoint | general |
| Create a project called Atlas | work |
| /replay fix date | work |
| delete all missions | work |
| Retention: Unknown. “Not project memory” does not mean “not stored”. Account selected by Core. Usage: Unknown. | Conservazione: Sconosciuta. “Non è memoria di progetto” non vuol dire “non archiviato”. Account scelto dal Core. Utilizzo: Sconosciuto. |
| How this chat works | Come funziona questa chat |
| Replies and records stay in the project you chose. Effects are cards you confirm. | Risposte e record restano nel progetto scelto. Gli effetti sono schede che confermi. |
| General | Generale |
| Not project memory. “Remember in…” asks where, and writes only after you confirm. | Non è memoria di progetto. “Ricorda in…” chiede dove, e scrive solo dopo la tua conferma. |
| READ and NAVIGATE answer here and are not recorded. CREATE records one thing. PROPOSE only makes a card. | READ e NAVIGATE rispondono qui e non vengono registrati. CREATE registra una cosa. PROPOSE crea solo una scheda. |
| Refused | Rifiutato |
| Bulk approvals, shell commands, policy, credentials, deleting: “I can’t do that from chat; open Work.” | Approvazioni in blocco, comandi shell, policy, credenziali, eliminazioni: “Non posso farlo dalla chat; apri Lavoro.” |
| Retention | Conservazione |
| Unknown | Sconosciuta |
| Try it | Provalo |
| A button fills the field; nothing is sent until you press Send. | Un pulsante riempie il campo; non si invia nulla finché non premi Invia. |
| Card gallery | Galleria delle schede |
| Examples with their buttons off. The same cards appear in the conversation, where they work. | Esempi con i pulsanti spenti. Le stesse schede compaiono nella conversazione, dove funzionano. |
| Plan card | Scheda del piano |
| Start card | Scheda di avvio |
| Approval card | Scheda di approvazione |
| No decision is waiting now. | Nessuna decisione è in attesa adesso. |
| Status card | Scheda di stato |
| Edge cases | Casi limite |
| One-shot fixtures for the next send. A failed send is retried with the same key and recorded once. Sending the same text twice within 2 s asks first. | Casi di prova per il prossimo invio. Un invio fallito si ritenta con la stessa chiave e si registra una volta. Inviare lo stesso testo due volte entro 2 s chiede prima. |
| Slow reply (3 s) | Risposta lenta (3 s) |
| Failed send | Invio fallito |
| Open conversation | Apri la conversazione |
| Chat with Archeus | Chat con Archeus |
| Collapse | Riduci |
| Expand | Espandi |
| Simulated keyboard | Tastiera simulata |
| Hide keyboard | Nascondi la tastiera |

## Replay: page and recovery cards

Status: to review. 51 strings.

| English | Italian |
|---|---|
| Recorded steps | Passi registrati |
| settled by {w} | chiuso da {w} |
| Filter by category | Filtra per categoria |
| All | Tutte |
| Step cursor. Arrows step, Home and End jump | Cursore dei passi. Le frecce spostano, Home e Fine saltano |
| What Core recorded, in order. Each step carries a Replay category and, for a settlement, who settled it. Nothing here plays by itself and nothing can be re-run. | Ciò che il Core ha registrato, in ordine. Ogni passo ha una categoria Replay e, per una chiusura, chi l'ha chiusa. Qui nulla parte da solo e nulla si può rieseguire. |
| Cursor | Cursore |
| Older steps were pruned from the event log, so anything before them is UNKNOWN, not “nothing happened”. | I passi più vecchi sono stati eliminati dal registro eventi, quindi ciò che li precede è SCONOSCIUTO, non “non è successo nulla”. |
| Why this category | Perché questa categoria |
| none recorded | nessuna registrata |
| Recorded by | Registrato da |
| you (device) | te (dispositivo) |
| Read only, from the recorded edge and its event actor ({r}). Not a new record. | Sola lettura, dal passaggio registrato e dal suo attore ({r}). Non è un nuovo record. |
| A report is never the completion signal. A decision is never proof that it happened. | Un rapporto non è mai il segnale di completamento. Una decisione non è mai la prova che sia avvenuta. |
| How should we proceed with “{t}”? The outcome of its last attempt is uncertain. | Come procediamo con “{t}”? L'esito dell'ultimo tentativo è incerto. |
| Not done: add the changed instructions or the question first | Non fatto: aggiungi prima le istruzioni modificate o la domanda |
| Approved: the question for you was added to the conversation. Evidence unchanged. | Approvata: la domanda per te è stata aggiunta alla conversazione. Prove invariate. |
| Approved: {n}. The simulation moves on through its own steps; the evidence above is unchanged. | Approvata: {n}. La simulazione prosegue con i suoi passi; le prove qui sopra restano invariate. |
| Archeus would | Archeus farebbe |
| Archeus will not | Archeus non farà |
| Draft a proposal | Prepara una proposta |
| Question for you (unsent) | Domanda per te (non inviata) |
| Changed instructions | Istruzioni modificate |
| Bound to {t}, step {n}. Nothing will run or be sent until you approve. A retry is a new execution id. | Legata a {t}, passo {n}. Non girerà né sarà inviato nulla finché non approvi. Un nuovo tentativo è una nuova esecuzione. |
| Approve proposal | Approva la proposta |
| Recovery | Recupero |
| Options depend on where the mission is now. Each one makes an approval card; none re-runs, resumes or reconciles by itself. | Le opzioni dipendono da dove si trova ora la missione. Ognuna crea una scheda di approvazione; nessuna riesegue, riprende o riconcilia da sola. |
| What Archeus will not do, ever | Cosa Archeus non farà, mai |
| Starting state | Stato iniziale |
| From three commit bindings, otherwise UNKNOWN. There is no per-attempt starting digest. | Da tre legami a commit, altrimenti SCONOSCIUTO. Non esiste un digest iniziale per tentativo. |
| Retention depth | Profondità di conservazione |
| This read | Questa lettura |
| Oldest retained event | Evento più vecchio conservato |
| none | nessuno |
| Events kept | Eventi conservati |
| {n} days | {n} giorni |
| Open-mission extension | Estensione per missioni aperte |
| not built: “kept until the mission closes + 30 days” does not exist yet | non costruita: “conservato fino alla chiusura + 30 giorni” non esiste ancora |
| Steps are read from rows, not the event log. A range past retention answers UNKNOWN with a reason, never “nothing happened”. | I passi si leggono dalle righe, non dal registro eventi. Un periodo oltre la conservazione risponde SCONOSCIUTO con un motivo, mai “non è successo nulla”. |
| External effects: UNKNOWN. No Effect record exists. | Effetti esterni: SCONOSCIUTO. Non esiste un record Effect. |
| Five example rows | Cinque righe di esempio |
| The strategy’s example day, each row answered with what Core records today. An example, not this mission. | La giornata d'esempio della strategia, ogni riga con ciò che il Core registra oggi. Un esempio, non questa missione. |
| Records now | Record attuali |
| Machine | Macchina |
| The vocabulary | Il vocabolario |
| states | stati |
| machines | macchine |
| One table in Core covers every state of every machine; a state with no entry answers UNKNOWN. execution.ENDED_REJECTED is RECORDED (owner clarification, 2026-10-25). Source notes stay in English. | Una sola tabella nel Core copre ogni stato di ogni macchina; uno stato senza voce risponde SCONOSCIUTO. execution.ENDED_REJECTED è REGISTRATO (chiarimento del proprietario, 2026-10-25). Le note sulle fonti restano in inglese. |
| Not every external effect can be reversed. | Non ogni effetto esterno si può annullare. |
| The simulation moved 10 minutes forward. Replay shows its new steps. | La simulazione è avanzata di 10 minuti. Il Replay mostra i suoi nuovi passi. |
| Advance the simulation 10 minutes | Avanza la simulazione di 10 minuti |

## Terminal view: reply lines

Status: to review. 25 strings.

| English | Italian |
|---|---|
| Not done:  | Non fatto:  |
| Running ${c.running}, waiting for you ${c.waiting}, stopped ${c.stopped}. Accepting new work: Unknown. | In corso ${c.running}, aspettano te ${c.waiting}, fermi ${c.stopped}. Accetta nuovo lavoro: Sconosciuto. |
| Unknown is never shown as 0. | Sconosciuto non è mai mostrato come 0. |
| Route decision ${c.id}. Served model and billed cost: Unknown. Account: selected by Core. | Decisione di instradamento ${c.id}. Modello servito e costo fatturato: Sconosciuti. Account: scelto dal Core. |
| +${c.more} more | +${c.more} altri |
| Started. Planning is under way; the plan waits for your approval before anything executes. | Avviata. La pianificazione è in corso; il piano aspetta la tua approvazione prima che si esegua qualcosa. |
| Kept as a mission. Not started. | Tenuta come missione. Non avviata. |
| Proposed. Nothing has started. Planning runs on an account Core selects; the plan then waits for your approval. | Proposta. Non è partito nulla. La pianificazione gira su un account scelto dal Core; il piano poi aspetta la tua approvazione. |
| Started (simulated). | Avviata (simulato). |
| Kept. Not started. | Tenuta. Non avviata. |
| Done for ${c.n \|\| c.targets.length}: ${names}. | Fatto per ${c.n \|\| c.targets.length}: ${names}. |
| New dispatch stays blocked until you re-arm (E on the terminal, or Settings). | Ogni nuovo avvio resta bloccato finché non riarmi (E nel terminale, o Impostazioni). |
| Confirm: ${v.toLowerCase()} ${names} now? Step 2 of 2. This cannot be undone from here. | Conferma: ${v.toLowerCase()} ${names} adesso? Passo 2 di 2. Da qui non si può disfare. |
| Done (simulated). | Fatto (simulato). |
| ${v} ${names}? Nothing has happened yet.${two ? ' Step 1 of 2.' : ''} | ${v} ${names}? Non è successo ancora nulla.${two ? ' Passo 1 di 2.' : ''} |
| Confirmed (simulated). | Confermato (simulato). |
| Dismissed. | Scartata. |
| Why it asks:  | Perché lo chiede:  |
| Only the decision screen decides; this message never does. | Decide solo la schermata della decisione; questo messaggio non decide mai. |
| Remembered:  | Ricordato:  |
| Remember in  | Ricorda in  |
| Remembered (simulated). | Ricordato (simulato). |
| Nothing is written until you choose where:  | Non si scrive nulla finché non scegli dove:  |
| General answer, not project memory. "Not project memory" does not mean "not stored". | Risposta generale, non memoria di progetto. "Non è memoria di progetto" non vuol dire "non archiviato". |
| Nothing was created or sent yet. | Non è stato creato né inviato nulla. |

## Terminal view: keys and messages

Status: to review. 14 strings.

| English | Italian |
|---|---|
| 1 | now |
| 2 | work |
| 3 | world |
| a | attention |
| r | replay |
| 4 | control |
| now | work |
| CREATED | PAUSED |
| control | decision |
| map | list |
| list | feed |
| map | detail |
| list | map |
| list | detail |

## Terminal view: screens

Status: to review. 46 strings.

| English | Italian |
|---|---|
| done | inactive |
| active | verifying |
| planning | approved |
| Decide | asks you to decide |
| Review | results to accept |
| Unblock | work that needs a person |
| outcome | o |
| plan | p |
| now | n |
| evidence | e |
| why | w |
| timeline | t |
| relations | r |
| accounts | Accounts |
| automations | Automations |
| clients | Clients |
| security | Security |
| health | Health |
| appearance | Appearance |
| about | About |
| done | Ok |
| paused | Off |
| blocked | Open |
| needs_you | Needs attention |
| inactive | Unknown |
| Never push, never touch credentials: Archeus does not read, store, copy, inject or relay subscription tokens. | Decisions are the owner's: chat proposes; only a card on screen with its hash is decided. |
| Prototype | V2 Live, a simulation |
| Core | none connected |
| ↑ ↓  j k | move |
| Enter | open |
| Esc  b | back |
| Tab | next pane or tab (Shift+Tab back) |
| 1 2 3 a r 4 | Now, Work, World, Attention, Replay, Control |
| g | places: every screen by letter |
| : or / | command line: go to, or a slash command |
| t | tell Archeus (opens the command line) |
| [ ]  PgUp PgDn | page |
| A  R  C  P  X | the actions on the bottom line; decisions ask y first |
| E | emergency stop: stop every running mission and block new dispatch; E again re-arms (asks y) |
| n N | next or previous mission in Replay |
| ? | this help |
| q | back; on Now it leaves the terminal view |
| READ | NAVIGATE |
| s | security |
| h | health |
| u | accounts |

## Areas pages

Status: to review. 29 strings.

| English | Italian |
|---|---|
| ok | Allowed |
| attention | Asks you |
| paused | Denied |
| attention | Denied by policy only |
| blocked | Unguarded |
| blocked | Not confined |
| Never push, never touch credentials | Archeus does not read, store, copy, inject or relay subscription tokens. |
| Decisions are the owner's | Chat proposes; only a card on screen with its hash is decided. |
| No silent approval | A new mission from chat waits for a card here (V1 today starts it; flagged G1). |
| low | critical |
| active | On track, more than 20% left |
| attention | Low, 20% or less left |
| blocked | Almost out, 5% or less |
| unknown | Unknown, never 0 |
| ask | Ask on risky actions |
| plan | Plan only, never execute |
| auto | Approve low risk automatically |
| auto | Automatic, by failover order |
| 10 | 10% left |
| 20 | 20% left |
| 30 | 30% left |
| x-hooks | Hooks |
| x-mcp | MCP servers |
| x-agents | Agents |
| x-autos | Automations |
| x-clients | Clients |
| since | Since you last looked |
| today | Today |
| blocked | failed |

## Inspectors

Status: to review. 18 strings.

| English | Italian |
|---|---|
| outcome | Outcome |
| plan | Plan |
| now | Now |
| evidence | Evidence |
| why | Why |
| timeline | Timeline |
| relations | Relations |
| overview | Overview |
| route | Route |
| output | Output |
| checkpoints | Checkpoints |
| facts | Facts |
| decision | Decision |
| policy | Policy |
| checks | Checks |
| path | Path |
| item | Item |
| project | Project |

## Area inspectors

Status: to review. 7 strings.

| English | Italian |
|---|---|
| ok | Connected |
| active | Connecting |
| paused | Disabled |
| unknown | Unknown |
| account | Account |
| usage | Usage |
| Sign in | A subscription login. Archeus never reads, stores, copies, injects or relays the token. |

## Crystal map and mission graph (visual fidelity pass)

Status: to review. Builder-written, not checked by a native speaker.

| English | Italian |
|---|---|
| EXECUTION | ESECUZIONE |
| VERIFICATION | VERIFICA |
| REVIEW | REVISIONE |
| TASK | ATTIVITÀ |
| OUTPUT | RISULTATO |
| MISSION | MISSIONE |
| Branch: {name} | Ramo: {name} |
| No items yet | Ancora nessuna voce |

## Calm band and panels (n1)

Status: to review. Builder-written, not checked by a native speaker.

| English | Italian |
|---|---|
| Today | Oggi |
| Known projects | Progetti noti |
| Tell | Dì |
| Today and known projects | Oggi e progetti noti |
| Understand · Plan · Do | Capisci · Pianifica · Fai |
| items | voci |
| {n} items / {n} item | {n} voci |
| {n} verified | {n} verificata / verificate |

## Phone bottom bar and Places sheet (n1)

Status: to review. Builder-written, not checked by a native speaker.

| English | Italian |
|---|---|
| Places | Luoghi |

## Accessibility fixes (2026-10-27): to review

- Emergency stop all missions → Arresto di emergenza di tutte le missioni
- Re-arm new work → Riarma il nuovo lavoro

## Overview rework (2026-10-27): to review

- Tell Archeus what to do… → Dì ad Archeus cosa fare… (the field placeholder of the Tell dock and the Chat page; replaces Tell Archeus what you need… / Dimmi cosa ti serve…)
- Decision notes on the Overview → Note sulle decisioni in Panoramica (the toolbar switch; replaces the string that named the Map as well)
- Removed with the Map screen: Map → Mappa, Constellation → Costellazione.
## One Work page with its graph (2026-10-27, builder B): to review

File: `js/i18n-work.js`. Attention is no longer a page; its words live on Work.

- All projects → Tutti i progetti
- Work graph → Grafo del lavoro
- Work graph: missions and decisions grouped by what they wait on. The list below has the same content. → Grafo del lavoro: missioni e decisioni raggruppate per ciò che attendono. L'elenco qui sotto ha lo stesso contenuto.
- One page for Work and Attention: missions and decisions grouped by what they wait on, as a graph and as a list. The spine shows where each mission is (A13); an obligation is a 12 % amber tint with its state in words (B09). → Una sola pagina per Lavoro e Attenzione: missioni e decisioni raggruppate per ciò che attendono, come grafo e come elenco. La spina mostra a che punto è ogni missione (A13); un obbligo è una tinta ambra al 12 % con lo stato a parole (B09).
- N more are in Replay and Work. → Altri N sono in Replay e Lavoro. (rule in `js/i18n-areas.js`, was "Replay and Attention")
# Projects concept rebuild — 2026-10-27 (to review)

Builder translations; no native review. Source: `js/i18n-insp.js`.

| English | Italian |
|---|---|
| Projects scene | Scena dei progetti |
| Select a project to see its phases, missions and ideas. | Seleziona un progetto per vedere fasi, missioni e idee. |
| No projects yet. | Ancora nessun progetto. |
| No missions yet. | Ancora nessuna missione. |
| No project ideas yet. | Ancora nessuna idea per questo progetto. |
| Project ideas | Idee del progetto |
| Phases | Fasi |
| Recorded relation | Relazione registrata |
| Suggested relation | Relazione suggerita |
| Active / Waiting / Verified / Completed | Attiva / In attesa / Verificata / Completata |
| Nothing running in this project. | Niente in esecuzione in questo progetto. |
| Work needs you in this project. | Il lavoro in questo progetto richiede la tua attenzione. |
| Work is active in this project. | Il lavoro in questo progetto è attivo. |
| Every mission is completed. | Tutte le missioni sono completate. |
| Capture an idea | Cattura un’idea |
| Idea title | Titolo dell’idea |
| Capture / Promote | Cattura / Promuovi |
| Phase summary across missions | Riepilogo delle fasi delle missioni |
| Advance along the idea path | Avanza nel percorso dell’idea |
| No launch settings recorded. | Nessuna impostazione di avvio registrata. |
| N mission / N missions | N missione / N missioni |

## Chat workspace page (2026-10-28, Codex): to review

File: `js/i18n-chat.js`. Dynamic label: `{n} unread` → `{n} non letti`.

- Conversation workspace → Spazio di conversazione
- Conversations → Conversazioni
- Search conversations → Cerca conversazioni
- Projects → Progetti
- Missions → Missioni
- Context → Contesto
- No conversations match → Nessuna conversazione corrispondente
- No messages here yet → Ancora nessun messaggio qui
- Mission focus shows linked messages. Replies go to the project. → La vista della missione mostra i messaggi collegati. Le risposte vanno al progetto.
- Mission focus · Replies go to the project → Vista missione · Le risposte vanno al progetto
- Current state → Stato attuale
- Active mission → Missione attiva
- No active mission → Nessuna missione attiva
- Pinned decisions → Decisioni fissate
- No pinned decisions → Nessuna decisione fissata
- Command reference → Guida ai comandi
- Search commands → Cerca comandi
- No commands match → Nessun comando corrispondente
- Archeus is working → Archeus sta lavorando
- Simulation fixtures → Scenari di simulazione
- Privacy and storage → Privacy e conservazione
- Pin decision → Fissa decisione
- Unpin decision → Rimuovi decisione dai fissati
- Draft a command → Prepara un comando
- Emergency stop engaged → Arresto di emergenza attivo
- Completed → Completato
- Waiting → In attesa
- Position unknown → Posizione sconosciuta
- Cancelled → Annullata

## Security policy notes, standalone forms (2026-10-28): to review

File: `js/i18n-areas.js`. The notes were only translated joined to their source (for example "Policy. Only Core dispatches."); the new Security page shows them alone, so each has its own key now. The Italian is the second half of the old joined pair.

- Inside the execution workdir only. → Solo dentro la cartella di lavoro dell’esecuzione.
- Anything outside is denied, and a hook that cannot answer denies. → Tutto ciò che sta fuori è negato, e un hook che non sa rispondere nega.
- With the stripped environment. → Con l’ambiente ripulito.
- A push is a separate action. → Il push è un’azione a parte.
- Stops and asks you with the exact command. → Si ferma e ti chiede, con il comando esatto.
- The hook is off, so a push goes ahead without asking you. → L’hook è spento: un push parte senza chiederti nulla.
- Asks with the package name. → Chiede indicando il nome del pacchetto.
- Only Core dispatches. → Solo il Core avvia.
- Denied by policy, not by the OS: physical reach is not built (finding G1). → Negato dalla policy, non dal sistema operativo: il raggio d’azione fisico non è costruito (rilievo G1).
- Provider access is not brokered yet and the network is not walled off. → L’accesso al provider non passa ancora da un broker e la rete non è isolata.

## Overview territories, focus and view switch — 2026-10-28: to review

File: `js/i18n-now.js`. Not checked by a native speaker.

- All projects → Tutti i progetti
- Open work → Apri il lavoro
- Show missions → Mostra le missioni
- Open mission → Apri la missione
- Projects view / Network view → Vista a progetti / Vista a rete
- No missions yet → Ancora nessuna missione
- Archeus has not completed a mission today. → Oggi Archeus non ha ancora completato nessuna missione.
- Archeus completed N missions today: → Oggi Archeus ha completato N missioni:
- +N more projects → +N altri progetti
- N missions, N ideas captured → N missioni, N idee raccolte
- N projects. M need you. → N progetti. Ne servono M a te.
- Action verbs after “Archeus”: completed → ha completato; is verifying → sta verificando; is reviewing → sta rivedendo; started → ha avviato; asks you to approve → ti chiede di approvare; is blocked on → è bloccato su; has stopped → ha fermato; paused → ha messo in pausa

## Security, Health, Usage and Accounts overhaul (2026-10-28): to review

File: `js/i18n-areas.js`. New or changed visible strings. Existing strings that moved (labels, notes, column names such as 5 hour window, Week, Status) keep their earlier Italian.

| English | Italian |
|---|---|
| 1 check needs attention / N checks need attention | 1 controllo richiede attenzione / N controlli richiedono attenzione |
| N unknown | 1 sconosciuto / N sconosciuti |
| Every check is OK | Tutti i controlli sono OK |
| 1 account is low / N accounts are low | 1 account è basso / N account sono bassi |
| Every account has room (sentence, no full stop) | Ogni account ha margine |
| <Account> takes the next mission (sentence, no full stop) | <Account> prende la prossima missione |
| No account can take new work | Nessun account può prendere nuovo lavoro |
| Last hour (Usage column) | Ultima ora |
| Show all N / Show fewer | Mostra tutti (N) / Mostra meno |
| Open project | Apri il progetto |
| 1 project / N projects (approval mode groups; the group of projects without their own settings is labelled Default) | 1 progetto / N progetti |
| Every project starts with the default. Only a project that differs has its own row. | Ogni progetto parte con le impostazioni predefinite. Solo un progetto che differisce ha una riga propria. |
| Give a project its own settings (select) | Dai a un progetto impostazioni proprie |
| Project that gets its own settings (label) | Progetto che riceve impostazioni proprie |
| Use the default | Usa il predefinito |
| Back to the default (simulated). | Tornato al predefinito (simulato). |
| This project now has its own launch settings (simulated). | Questo progetto ha ora impostazioni di avvio proprie (simulato). |
| + N more (names of projects in a group) | + altri N |

## Page overhaul A: Projects, Work, Replay, Chat, inspectors (2026-10-28): to review

File: `js/i18n-insp.js` (exact strings and counting rules). Existing words (Needs you, Running, Quiet, Waiting, Active, Verified, Captured, Done, Mission, Command reference) are reused.

- Open work → Apri il lavoro
- Archeus has not acted here yet. → Archeus non ha ancora agito qui.
- Search projects → Cerca progetti
- No project matches. → Nessun progetto corrisponde.
- Captured ideas → Idee catturate
- Recent → Recenti
- Missions of the other projects: search by title. → Le missioni degli altri progetti: cerca per titolo.
- N projects → N progetti (1 progetto)
- N need you / N needs you → N richiedono te (1 richiede te)
- N running → N in corso
- N ideas → N idee (1 idea)
- Show all N → Mostra tutti (N)
- Graph shows the first 12 of N missions, the list has all → Il grafico mostra le prime 12 missioni su N, l’elenco le ha tutte
- No missions to replay yet. → Ancora nessuna missione da rivedere.

## Shell, Extensions, Settings and Terminal overhaul (2026-10-28, builder C): to review

- All {N} projects (rail and Places sheet, when there are more projects than fit) → Tutti i {N} progetti
- {N} extensions (Extensions summary) → {N} estensioni
- {N} off (Extensions summary) → {N} spente
- 1 needs you (Extensions summary and group headers; the plural form {N} need you already existed) → 1 ti serve
- Back to the app (terminal view exit button, label App) → Torna all’app
- Show / Hide (Decision notes choice in Settings) → Mostra / Nascondi
- Live work moves the map slowly: nodes drift, markers travel along active links and the core mark breathes. Reduced motion stops all of it. (replaces the older "the core mark is the one thing that moves" note) → Il lavoro in corso muove piano la mappa: i nodi si spostano appena, i segnalini viaggiano lungo i collegamenti attivi e il simbolo del Core respira. Il movimento ridotto ferma tutto.
- Simulated clock → Orologio simulato
- . One real second is ten simulated seconds at x1. Same seed, same story. → . Un secondo reale sono dieci secondi simulati a x1. Stesso seme, stessa storia.
- V2 Live is a prototype that simulates the Archeus app on every device. Nothing here is connected to a Core: the projects, missions, approvals, usage numbers and replies are fixtures and a scripted clock. → V2 Live è un prototipo che simula l’app Archeus su ogni dispositivo. Nulla qui è collegato a un Core: i progetti, le missioni, le approvazioni, i numeri di utilizzo e le risposte sono dati di prova e un orologio scritto.
- Six looks: Dark and Light, each standard and high contrast, plus System and forced colours. Reduced motion is Quiet (A05). → Sei aspetti: Scuro e Chiaro, ciascuno standard e ad alto contrasto, più Sistema e colori forzati. Il movimento ridotto è Quieto (A05).
- Everything on screen is simulated and says so; no Core is connected. → Tutto ciò che è sullo schermo è simulato e lo dice; nessun Core è collegato.

Extensions tabs and Settings sections (second pass, same day):

- Nothing needs you (Extensions state sentence) → Niente ti serve
- {N} need you (plural, sentence part) → {N} ti servono
- Last seen (clients column) → Visto l’ultima volta
- Search extensions / Search extensions… (label, placeholder) → Cerca estensioni / Cerca estensioni…
- No extension matches. / Clear search → Nessuna estensione corrisponde. / Cancella la ricerca
- Nothing is listed here. → Qui non c’è ancora nulla.
- Extension types (tab list label) → Tipi di estensione
- Open review (Needs you band, an agent whose result waits) → Apri la revisione
- Today HH:MM / Yesterday HH:MM / Earlier HH:MM (last activity) → Oggi HH:MM / Ieri HH:MM / Prima HH:MM
- Undo (toast after a switch-off) → Annulla
- Settings sections / Safety / Prototype / About (left nav) → Sezioni delle impostazioni / Sicurezza / Prototipo / Informazioni

Shell round two (rail groups, command palette, relative time):

- Govern / Configure (rail group labels; Work already existed) → Governa / Configura
- Search or run a command (top-bar button) → Cerca o esegui un comando
- Search pages, actions and projects (palette field) → Cerca pagine, azioni e progetti
- Command palette / Results / Pages / Actions → Comandi rapidi / Risultati / Pagine / Azioni
- Nothing matches. Try a page, an action or a project name. → Nessun risultato. Prova il nome di una pagina, di un’azione o di un progetto.
- move / run / close (palette footer, after the arrow and Enter and Esc keys) → muovi / esegui / chiudi
- Stop all / Tell Archeus → Ferma tutto / Dì ad Archeus
- Settings: Safety / Appearance / Prototype → Impostazioni: Sicurezza / Aspetto / Prototipo
- Language: Italiano / Language: English → Lingua: Italiano / Lingua: English
- Stale (state vocabulary) → Non aggiornato
- Ctrl+K or Cmd+K, Search pages, actions and projects, and run them (keyboard help) → Ctrl+K o Cmd+K, Cerca pagine, azioni e progetti ed eseguili
- Mon, Tue, Wed, Thu, Fri, Sat, Sun before a time (Mon 14:20) → Lun, Mar, Mer, Gio, Ven, Sab, Dom

## Network view clusters (2026-10-28, agent N): to review

File: `js/i18n-now.js`. The map's other strings (Needs you, Running, Project, Mission, Agent execution, Zoom in, Zoom out, Fit) were already translated; `Reset map view` was removed with its button (Fit also resets the view).

- Open work → Apri il lavoro (last line of a project's preview card)
- Open mission → Apri la missione (last line of a mission's preview card)
- No missions yet → Ancora nessuna missione (hub label of a project with no missions)
- +N quiet → +N inattive (the count of idle or finished missions folded into a hub; the Italian is a short form of "missioni inattive")

## Work, Replay, Projects and the Attention strip — 2026-10-28

Status: **to review**. Source: `js/i18n-work.js`. Rules (with a number) are written as a pattern.

| English | Italian |
|---|---|
| Saved views | Viste salvate |
| Layout | Disposizione |
| List / Graph | Elenco / Grafo |
| Find a project | Cerca un progetto |
| All (a view tab) | Tutto |
| Running (a view tab and a group) | In corso |
| N missions and decisions | N missioni e decisioni |
| Showing N of M | Mostro N di M |
| Selected work | Lavoro selezionato |
| What Archeus did | Cosa ha fatto Archeus |
| Select a row to see what Archeus did. | Scegli una riga per vedere cosa ha fatto Archeus. |
| awaiting input / active / pending / error / complete / stale (the shared state vocabulary, lower case) | in attesa di te / attivo / in sospeso / errore / completo / fermo |
| Nm ago, Nh ago, Nd ago, now | N min fa, N h fa, N g fa, ora |
| Nothing is stuck. | Niente è bloccato. |
| Nothing has finished yet. | Non è ancora finito nulla. |
| No work yet. | Ancora nessun lavoro. |
| No work in X yet. | Ancora nessun lavoro in X. |
| See what is running | Vedi cosa è in corso |
| Tell Archeus what to do | Dì ad Archeus cosa fare |
| Pausing “X”. (toast, with Undo) | Messa in pausa: “X”. |
| One page for Work and Attention: missions and decisions grouped by what they wait on, as a list with a detail pane and as a graph. … | Una sola pagina per Lavoro e Attenzione: … come elenco con un pannello di dettaglio e come grafo. … |
| Sections / View / Detail | Sezioni / Vista / Dettaglio |
| Timeline / Compact | Cronologia / Compatta |
| Normal / Thinking / Verbose (detail levels; Thinking is Ragionamento here, not the mission state In pianificazione) | Normale / Ragionamento / Dettagliata |
| Events / Evidence / Recovery / Reference | Eventi / Prove / Recupero / Riferimenti |
| N steps recorded | N passi registrati |
| HH:MM to HH:MM | HH:MM a HH:MM |
| Last: plan APPROVED | Ultimo: plan APPROVED (the Core state names stay English) |
| 1 step needs a look / N steps need a look | 1 passo da guardare / N passi da guardare |
| N steps (a compact row) | N passi |
| trigger X · by Y · seq N (Verbose) | causa X · da Y · seq N |
| mission CREATED to EXECUTING (a compact row) | mission CREATED a EXECUTING |
| Sort projects | Ordina i progetti |
| Attention / Recent / Name | Attenzione / Recenti (existing) / Nome |
| Activity | Attività |
| N of M projects | N di M progetti |
| Showing the latest 30 changes. | Mostro gli ultimi 30 cambiamenti. |
| Projects that need you | Progetti che hanno bisogno di te |
| +N more | +N altri (+1 altro) |

## Chat redesign, builder A (2026-10-28): to review

Strings built inline with `L(en, it)` in `js/chat.js`, `js/chat-cards.js` and `js/picker.js`. The old rail, context column and pin strings were removed from `js/i18n-chat.js`.

- To → A (prefix of the scope chip: "To Archeus")
- Destination → Destinazione (accessible name of the scope picker)
- General → Generale
- Not project memory → Non è memoria di progetto
- Projects → Progetti (group)
- Needs you → Richiede te (group header)
- Search → Cerca (picker search field)
- Nothing matches. → Nessun risultato.
- Replies and records stay in {p}. → Risposte e record restano in {p}.
- Nothing here is saved to a project. → Qui non si salva nulla in un progetto.
- Command · /{n} · {c} → Comando · /{n} · {c}
- All missions → Tutte le missioni
- Mission → Missione
- Open / Closed (mission picker groups) → Aperte / Chiuse
- {n} open → {n} aperte
- Nothing open → Niente di aperto
- More (menu button) → Altro
- Needs you · {n} → Richiede te · {n}
-  · step {n} of 6 → · passo {n} di 6
- Chat sections → Sezioni della chat
- Conversation / Receipts / Context (tabs) → Conversazione / Ricevute / Contesto
- Ask anything. → Chiedi pure.
- Ask a question. No mission starts from General. → Fai una domanda. Da Generale non parte nessuna missione.
- Nothing said in {p} yet. → Ancora nulla detto in {p}.
- Ask, or hand Archeus work. Replies and receipts appear here. → Chiedi, o affida un lavoro ad Archeus. Risposte e ricevute compaiono qui.
- Explain a checkpoint → Spiega un checkpoint (starter chip; the same text is sent)
- What can you do? → Cosa sai fare?
- What needs me? → Cosa aspetta me?
- Status → Stato
- Start a mission… → Avvia una missione…
- Capture an idea… → Cattura un'idea…
- Waiting for you → Aspettano te
- Approve this plan? / Allow this action? → Approvare questo piano? / Consentire questa azione?
- Last receipts → Ultime ricevute
- Done by Archeus → Fatto da Archeus
- General keeps no receipts. → Generale non tiene ricevute.
- Answers here do not touch a project. Pick a project to see what Archeus did in it. → Le risposte qui non toccano nessun progetto. Scegli un progetto per vedere cosa ha fatto Archeus.
- Archeus has not acted here yet. → Archeus non ha ancora agito qui.
- Show {n} earlier → Mostra {n} precedenti
- Commands / Search commands / No command matches. → Comandi / Cerca comandi / Nessun comando corrispondente.
- No missions yet. → Ancora nessuna missione.
- just now / {n} min ago / {n} h ago → adesso / {n} min fa / {n} h fa (relative time on the simulation clock; the exact time is the tooltip)
- Commands (type /) → Comandi (scrivi /) (tooltip of the slash button)
- Send (Enter) → Invia (Invio) (tooltip of Send)

## Security, Health, Usage and Accounts as parts of a page (2026-10-28, round 2): to review

File: `js/i18n-areas.js`. Each of the four pages now has parts that are links; these are the new or changed visible strings. Exact strings are in the dictionary, the ones with a number, a time or a name are patterns at the start of `RULES_AREAS`.

- Overview / Policy / Boundaries / Activity / Emergency (Security parts) → Panoramica / Regole / Confini / Attività / Emergenza (Policy already read Regole)
- All / Needs attention / Unknown / OK (Health filter) → Tutti / Richiede attenzione / Sconosciuto / OK
- Accounts / Windows / History (Usage parts) → Account / Finestre / Cronologia
- Accounts / Models / Failover / Launch settings (Accounts parts) → Account / Modelli / Failover / Impostazioni di avvio
- Security sections, Health filter, Usage views, Account sections (navigation names) → Sezioni della sicurezza, Filtro della salute, Viste dell'uso, Sezioni degli account
- needs you / engaged / low / needs attention (hidden words beside a dot) → ti serve / attivo / basso / richiede attenzione
- N of M actions → N azioni su M
- Held commands never auto-allow. Policy applies to every project. → I comandi trattenuti non si autorizzano mai da soli. Le regole valgono per ogni progetto.
- Scope: every project. Source: Archeus policy. Read only here. → Ambito: ogni progetto. Origine: regole di Archeus. Qui sono in sola lettura.
- The mode a new mission starts with. No per-project command overrides are recorded. → La modalità con cui parte una nuova missione. Nessuna deroga per progetto è registrata.
- Change it in Launch settings / See every action / See all events / See all N boundaries / Review the policy → Cambiala in Impostazioni di avvio / Vedi ogni azione / Vedi tutti gli eventi / Vedi tutti i N confini / Rivedi le regole
- Where policy ends and physical confinement would have to begin. → Dove finiscono le regole e dovrebbe iniziare il confinamento fisico.
- Security events; Every decision, hook and breaker change, newest first. → Eventi di sicurezza; Ogni decisione, hook e cambio di interruttore, dal più recente.
- After three failed starts in ten minutes a harness stops starting new work until it recovers. → Dopo tre avvii falliti in dieci minuti un harness smette di avviare nuovo lavoro finché non si riprende.
- just now / N min ago / N h ago (relative time; the exact time is in the tooltip, which stays numeric) → adesso / N min fa / N h fa
- Showing N of M / Showing all N (filtered and folded counts) → Mostra N di M / Mostra tutti (N)
- Run all / Check again / Stale → Esegui tutto / Controlla di nuovo / Non aggiornato
- Last run (existing, now followed by a relative time) → Ultima esecuzione
- Changed 3 min ago from OK / Checked 3 min ago / No change this session → Cambiato 3 min fa da OK / Controllato 3 min fa / Nessun cambiamento in questa sessione
- Name checked again (simulated). / Every check ran again (simulated). → Nome ricontrollato (simulato). / Ogni controllo è stato rieseguito (simulato).
- No check needs attention. / No check is unknown. / No check is OK. / Show all checks → Nessun controllo richiede attenzione. / Nessun controllo è sconosciuto. / Nessun controllo è OK. / Mostra tutti i controlli
- Six checks, each read from records. A missing reading is unknown, never 0. → Sei controlli, ognuno letto dai registri. Una lettura mancante è sconosciuta, mai 0.
- Headroom and reset (column) → Margine e azzeramento
- At this rate you reach the limit at HH:MM (in N min). → Con questo ritmo arrivi al limite alle HH:MM (tra N min).
- At this rate the 5 hour window does not run out. / No forecast yet: not enough readings. → Con questo ritmo la finestra di 5 ore non si esaurisce. / Ancora nessuna previsione: letture insufficienti.
- Your line; New work waits at N% left; Running work finishes; nothing new starts on an account at or under the line. → La tua soglia; Il nuovo lavoro attende al N% rimasto; Il lavoro in corso finisce; non parte nulla di nuovo su un account alla soglia o sotto.
- N% left · reset text; Reset time not recorded; No reading yet → N% rimasto · ...; Ora di azzeramento non registrata; Nessuna lettura
- The 5 hour window, as the share used. Read about every two minutes.; N% to M% used; No readings yet. Unknown is not zero. → La finestra di 5 ore, come quota usata. Letta circa ogni due minuti.; Dal N% al M% usato; Ancora nessuna lettura. Sconosciuto non è zero.
- Saved as you choose. / Each switch saves as you flip it. (autosave stated; three sentences that end this way) → Si salva appena scegli. / Ogni interruttore si salva appena lo cambi.
- Name is off. (toast with Undo) → Nome è disattivato.


## Chat queue and steer, builder A (2026-10-28): to review

Inline `L(en, it)` strings in `js/chat.js`, `js/chat-cards.js`, `chat-engine.js`; two Replay explanations in `js/i18n-chat.js`.

- Enter queue · {k}Enter steer → Invio accoda · {k}Invio guida (key hint; {k} is ⌘ or Ctrl+; shown only while a mission runs)
- {n} queued → {n} in coda
- Queued → In coda
- Handled after the current step. → Gestito dopo il passo corrente.
- Remove → Rimuovi
- Steering → Guida in corso
- Waiting for Core to acknowledge. Simulated. → In attesa che il Core confermi. Simulato.
- Removed from the queue. Nothing was sent. → Tolto dalla coda. Non è stato inviato nulla.
- Queued. It is handled after the current step. → In coda. Viene gestito dopo il passo corrente. (screen reader announcement)
- Steering. Waiting for Core to acknowledge; this is simulated. → Guida in corso. In attesa che il Core confermi; è simulato. (screen reader announcement)
- SIMULATED · Core acknowledged the steer for “{t}”. A real Core would record the request and the safe boundary where it took effect; here nothing changed course. → SIMULATO · Il Core ha confermato la richiesta di guida per “{t}”. Un Core reale registrerebbe la richiesta e il confine sicuro in cui ha avuto effetto; qui nulla ha cambiato rotta.
- Steer asked (simulated) → Guida richiesta (simulata) (Receipts line)
- Steer acknowledged (simulated) → Guida confermata (simulata) (Receipts line)
- Replay, steer request: A steer is a request to be taken at the next safe boundary. This is a simulation; a real Core would record the request, not that the mission changed course. → Una guida è una richiesta di essere presa al prossimo confine sicuro. Questa è una simulazione; un Core reale registrerebbe la richiesta, non che la missione abbia cambiato rotta.
- Replay, steer acknowledgement: Core acknowledged the steer. The acknowledgement is recorded; it does not prove the mission changed course, and the boundary it took effect at is not modelled here. → Il Core ha confermato la guida. La conferma è registrata; non prova che la missione abbia cambiato rotta, e il confine in cui ha avuto effetto qui non è modellato.

## Chat wide layout and slash pins, builder A (2026-10-28): to review

Inline `L(en, it)` strings in `js/chat.js`.

- Activity → Attività (name of the side pane on a wide Chat page)
- Open missions → Missioni aperte (Receipts, section heading)
- Pinned → Fissati (slash menu heading)
- Recent → Recenti (slash menu heading)
- Pin {c} → Fissa {c} (pin button name; {c} is the command, for example /stato)
- Unpin {c} → Rimuovi {c} dai fissati
- Pinned {c} → Fissato {c} (spoken when a pin is added)
- Unpinned {c} → Rimosso {c} dai fissati (spoken when a pin is removed)
- Alt+P pins or unpins the highlighted command → Alt+P fissa o rimuove il comando evidenziato (hint under the menu; not shown on the phone sheet)

## Replay: Recovery and Reference regrouped — 2026-10-28

Status: **to review**. Inline `L(en, it)` strings in `js/replay.js`.

| Recovery proposals (heading, now with one SIMULATED tag for the section) | Proposte di recupero |
| Recommended (the option that fits the mission now) | Consigliata |
| What Archeus would and will not do (disclosure on each option) | Cosa farebbe e cosa non farà Archeus |
| Not available now (options that do not apply, one line each) | Non disponibili ora |
| Where it stands (rail beside the options) | Dove siamo |
| Choose an option to draft a proposal. Nothing runs until you approve it. | Scegli un'opzione per preparare una proposta. Non gira nulla finché non la approvi. |
| How Replay reads Core (the two Decision notes, folded) | Come il Replay legge il Core |
## Simulated project count (Tools)
- Simulated projects → Progetti simulati (menu title)
- Number of simulated projects → Numero di progetti simulati (button name)
- 3 (the default story) → 3 (la storia predefinita)
- Reloads the prototype with that many projects and the same mission mix, to see how every page scales. → Ricarica il prototipo con quel numero di progetti e la stessa miscela di missioni, per vedere come scala ogni pagina.
## Work graph highlight — 2026-10-28
- Nothing matches this filter. → Nessun risultato per questo filtro.
- Clear filter → Azzera il filtro
- Filter by state (legend group name) → Filtra per stato
- Legend chips reuse the existing Needs you / Running / Blocked / Done words (Ti serve, In corso, Bloccate, Fatte).


## Harness as a facet of Accounts, Usage and Extensions (2026-10-28): to review

File: `js/i18n-areas.js`. "Harness" is kept in English (it is the product word in the UI); the names Claude Code, Codex and pi are not translated. Exact strings are in the dictionary, the ones with a count or a name are patterns at the start of `RULES_AREAS`.

- {n} harnesses / {n} accounts / {n} near the ceiling / {n} cannot take work (headline parts) → {n} harness / {n} account / {n} vicino al limite / {n} non può prendere lavoro
- Each harness has its own accounts, models, failover order and launch settings. A subscription login belongs to you. → Ogni harness ha i propri account, modelli, ordine di failover e impostazioni di avvio. Un accesso in abbonamento è tuo.
- Near its ceiling / Not verified / Ready / No account / Cannot start / No account can take work / Not installed (state words on a harness) → Vicino al limite / Non verificato / Pronto / Nessun account / Non può partire / Nessun account può prendere lavoro / Non installato
- Not detected → Non rilevato (version note of a harness that is not installed)
- {x} is not installed on this machine. → {x} non è installato su questa macchina.
- Install its CLI and Archeus detects it. It would support {list}. → Installa la sua CLI e Archeus la rileva. Supporterebbe {list}. (new capability names: Agents, Skills, Slash commands, Plugins, Sandbox profiles → Agenti, Competenze, Comandi slash, Plugin, Profili sandbox)
- Run Health after installing → Esegui Salute dopo l'installazione
- In failover order within {x}. {a} takes the next {x} mission. → In ordine di failover dentro {x}. {a} prende la prossima missione di {x}.
- No account is signed in for {x}. Sign in with its own CLI; Archeus never reads the token. → Nessun account ha effettuato l'accesso a {x}. Accedi con la sua CLI; Archeus non legge mai il token.
- The default is what a new {x} mission asks for. Saved as you choose. → Il predefinito è ciò che chiede una nuova missione di {x}. Si salva appena scegli.
- Order within each harness / Rules for every harness / Change order → Ordine dentro ogni harness / Regole per ogni harness / Cambia ordine
- An order only makes sense inside one harness: a run never fails over from one harness to another without asking. → Un ordine ha senso solo dentro un harness: un'esecuzione non passa da un harness a un altro senza chiedere.
- The run writes a checkpoint and continues on the next account of the same harness. → L'esecuzione scrive un checkpoint e continua sul prossimo account dello stesso harness.
- Starts with / Defaults for {x} → Parte con / Predefiniti di {x}
- Not supported by {x}. / Available in → Non supportato da {x}. / Disponibile in
- On in {x} / Off in {x} (a shared MCP server) → Attivo in {x} / Spento in {x}
- {n} of {m} in {x} (position in a failover order) → {n} di {m} in {x}
- Not tied to one harness: these apply to every harness. → Non legati a un harness: valgono per ogni harness.
- A kind of extension is offered only where a harness supports it. → Un tipo di estensione è offerto solo dove un harness lo supporta.
- The new ledes of Usage, Extensions and Launch settings, and the three notes that name a harness (Security approval mode, git push note, Health fix line "Or put another {x} account first in its failover order.") are in the same block of the dictionary.


## Network semantic zoom and worktrees (2026-10-28): to review
- Worktree → Worktree (kept in English: the Git word; the plural is the same)
- +3 worktrees → +3 worktree (chip on a project hub when its worktrees are folded away)
- 3 worktrees → 3 worktree (chip on a Projects cell; also its tooltip and spoken name)
- Worktrees → Worktree (heading of the list in a project's focus panel)
- linked → collegato (a worktree made by you or another tool; Archeus never deletes or resets it)
- task → attività (a worktree Archeus made for a task and removes after a verified merge)
- Active, Stale → Attivo, Obsoleto (existing words, reused for a worktree state)
- Missing → Mancante (the worktree folder is gone)
- Merged → Unito (the branch was merged)
- Abandoned → Abbandonato (the task was given up)
- Last activity → Ultima attività (hover card of a worktree)
- No mission → Nessuna missione (a worktree that holds no mission)
- Attempt → Tentativo (one run of a task, a small mark at the close zoom level)
- Task, Verification, Event → existing words, reused as kinds of the small marks at the close zoom levels
