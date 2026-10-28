// The Autopilot tour as data (AP01 to AP12). A chapter is { id, group, t, c, covers, env?, steps }: t and c are [English, Italian] (title and one-line caption),
// covers lists the SPEC row families the chapter shows (test/autopilot.test.mjs fails when a family has no chapter), steps run in order against the real DOM.
// A step is { do, target?, arg?, nth?, ms?, on?, optional? }: ms is the pause after it (read time at 1x), on limits it to 'desktop' or 'phone',
// optional is a feature another builder is still changing: a miss is logged and the caption stays quiet. The runner (autopilot.js) is the only code that touches the page.
// target: a data-key ('work-count'), a data-key prefix ('att-chip-*'), or any CSS selector (starts with [ . # or holds a space).

export const VERBS = ['nav', 'click', 'hover', 'unhover', 'type', 'clear', 'press', 'wait', 'select', 'reload'];

const N = (arg, ms = 700) => ({ do: 'nav', arg, ms });
const C = (target, ms = 800, o) => ({ do: 'click', target, ms, ...o });
const H = (target, ms = 1200, o) => ({ do: 'hover', target, ms, ...o });
const Y = (target, arg, ms = 700, o) => ({ do: 'type', target, arg, ms, ...o });
const K = (arg, ms = 600, o) => ({ do: 'press', arg, ms, ...o });
const W = (ms) => ({ do: 'wait', ms });
const U = { do: 'unhover', ms: 100 };
// A step that needs a prototype menu (device, theme, sim, projects) open first: the runner opens it if it is closed, as a person would, then acts on the item.
const TOOL = (tool, pick, ms = 900, o) => ({ do: 'click', tool, target: pick, ms, ...o });

const DOCK = 'chat-in-dock', SHEET_IN = 'chat-in-sheet';
const THEME = '.menu [role=menuitemradio], .tools [role=menuitemradio]';
const TOGGLE = '.menu [role=menuitemcheckbox], .tools [role=menuitemcheckbox]';
const SIMBTN = '.menu .col > .actions:nth-child(2) .btn, .tools .col > .actions:nth-child(2) .btn';
const OPEN_DECISION = '[data-key^="att-a-"] a.btn.primary';
const STOP = '[data-key="stop"], [data-key="bb-stop"]';

export const GROUPS = {
  start: ['Start', 'Inizio'], overview: ['Overview', 'Panoramica'], tell: ['Tell', 'Dimmi'], live: ['Parallel life', 'Vita in parallelo'], work: ['Work', 'Lavoro'], projects: ['Projects', 'Progetti'],
  chat: ['Chat', 'Chat'], replay: ['Replay', 'Replay'], pages: ['Govern and configure', 'Governo e configurazione'], terminal: ['Terminal view', 'Vista terminale'],
  quick: ['Quick actions and safety', 'Azioni rapide e sicurezza'], look: ['Look and scale', 'Aspetto e scala'], phone: ['Phone', 'Telefono']
};

export const CHAPTERS = [
  { id: 'welcome', group: 'start', t: ['Autopilot', 'Autopilot'], covers: ['A'],
    c: ['A guided tour of the real app. The simulation keeps running underneath. Pause, skip or stop at any time; a click or a key stops it.', 'Un giro guidato dell’app vera. La simulazione continua a girare sotto. Pausa, salta o ferma quando vuoi; un clic o un tasto la ferma.'],
    steps: [N('#/now', 3500)] },

  { id: 'ov-state', group: 'overview', t: ['State at a glance', 'Lo stato a colpo d’occhio'], covers: ['E', 'O', 'R', 'WP', 'I'],
    c: ['One sentence says what needs you, what runs and what stopped. Each project says what Archeus did there last.', 'Una frase dice cosa ti serve, cosa gira e cosa si è fermato. Ogni progetto dice cosa ha fatto Archeus per ultimo.'],
    steps: [N('#/now', 500), H('sentence', 1800), H('ledger', 1600, { optional: true }), H('att-chip-*', 1800, { optional: true }), U] },

  { id: 'ov-hover', group: 'overview', t: ['Hover cards and focus', 'Schede al passaggio e focus'], covers: ['R', 'Q'],
    c: ['Point at a project and the others step back; a card says what it holds. A click focuses the project and lists its missions.', 'Punta un progetto e gli altri si abbassano; una scheda dice cosa contiene. Un clic mette a fuoco il progetto e ne elenca le missioni.'],
    steps: [N('#/now', 500), H('.am-cell', 2000, { on: 'desktop', optional: true }), H('.am-cell', 1800, { nth: 1, on: 'desktop', optional: true }), C('.am-cell', 2200, { on: 'desktop', optional: true }), U] },

  { id: 'ov-network', group: 'overview', t: ['Projects or Network', 'Progetti o Rete'], covers: ['QN'],
    c: ['The switch beside the headline turns the territories into a network: every mission is a node around its project hub.', 'L’interruttore accanto al titolo trasforma i territori in una rete: ogni missione è un nodo attorno al suo progetto.'],
    steps: [N('#/now', 500), C('vs-network', 1800), H('.am-hit', 1600, { nth: 2, optional: true }), U] },

  { id: 'ov-zoom', group: 'overview', t: ['Semantic zoom', 'Zoom semantico'], covers: ['QN', 'Q'],
    c: ['Zoom in and the map shows more: names, then states, then the small marks of each attempt. Fit brings it all back.', 'Ingrandisci e la mappa mostra di più: nomi, stati, poi i segni di ogni tentativo. Adatta riporta tutto in vista.'],
    steps: [N('#/now', 500), C('vs-network', 900), C('[aria-label="Zoom in"]', 1000, { optional: true }), C('[aria-label="Zoom in"]', 1000, { optional: true }), C('[aria-label="Zoom in"]', 1200, { optional: true }),
      C('[aria-label="Fit all nodes"]', 1200, { optional: true }), C('vs-projects', 800)] },

  { id: 'ov-details', group: 'overview', t: ['Details drawer', 'Pannello dei dettagli'], covers: ['Q', 'N', 'P', 'E'],
    c: ['Details opens over the map, never squeezes it: counters, what is happening now and what changed since you last looked.', 'I dettagli si aprono sopra la mappa senza schiacciarla: contatori, cosa succede adesso e cosa è cambiato dall’ultima volta.'],
    steps: [N('#/now', 500), C('now-details-btn', 1800), H('m-*', 1400, { optional: true }), U, K('Escape', 600)] },

  { id: 'tell-slash', group: 'tell', t: ['Slash menu, pins and recents', 'Menu slash, fissati e recenti'], covers: ['F', 'PW'],
    c: ['Type / to see the commands by class. Pin the ones you use, and the recent ones come first. Up, Down and Enter work inside the list.', 'Scrivi / per vedere i comandi per classe. Fissa quelli che usi e i recenti vengono per primi. Su, Giù e Invio funzionano nell’elenco.'],
    steps: [N('#/now', 500), C(DOCK, 400), Y(DOCK, '/', 1200), K('ArrowDown', 500), K('ArrowDown', 500), C('.slash .spin', 900, { optional: true }), C('.slash .spin', 700, { optional: true }), Y(DOCK, 'mis', 1200), K('Escape', 400), { do: 'clear', target: DOCK, ms: 200 }] },

  { id: 'tell-mission', group: 'tell', t: ['Send a mission', 'Invia una missione'], covers: ['F'],
    c: ['Plain words become a mission. Archeus replies at once and the new work appears on the map and in Work, waiting for its plan.', 'Parole semplici diventano una missione. Archeus risponde subito e il nuovo lavoro compare sulla mappa e in Lavoro.'],
    steps: [N('#/now', 500), C(DOCK, 400), Y(DOCK, '/mission Add a shortcut list to Notes', 600), K('Enter', 2600)] },

  { id: 'tell-idea', group: 'tell', t: ['Capture an idea', 'Cattura un’idea'], covers: ['F'],
    c: ['An idea is not a mission. It is kept as a note with its own path, from Captured to Learned, until you decide.', 'Un’idea non è una missione. Resta come appunto, con il suo percorso da Catturata a Imparata, finché non decidi.'],
    steps: [N('#/now', 500), C(DOCK, 400), Y(DOCK, '/idea Let Replay be shared as a link', 600), K('Enter', 2400)] },

  { id: 'tell-confirm', group: 'tell', t: ['Effects ask first', 'Gli effetti chiedono prima'], covers: ['F'],
    c: ['Chat reads and creates; anything with an effect is a proposal. /estop makes a card, and nothing stops until you confirm.', 'La chat legge e crea; ogni cosa con un effetto è una proposta. /estop crea una scheda e nulla si ferma finché non confermi.'],
    steps: [N('#/now', 500), C(DOCK, 400), Y(DOCK, '/estop', 600), K('Enter', 2800), { do: 'click', target: '.tell-dock .ccard .btn.quiet, .tell-dock .ccard [data-key*="dismiss"], .tell-dock .ccard button:last-of-type', ms: 900, optional: true }] },

  { id: 'sim', group: 'live', t: ['Simulation controls', 'Controlli della simulazione'], covers: ['K', 'H'],
    c: ['The simulation is always running. Here the tour asks it for a decision, a failure and an offline spell; the same buttons are in the Sim menu.', 'La simulazione gira sempre. Qui il giro le chiede una decisione, un guasto e un periodo offline; gli stessi pulsanti sono nel menu Sim.'],
    steps: [N('#/now', 500), TOOL('sim', SIMBTN, 2200, { nth: 0 }), TOOL('sim', SIMBTN, 2200, { nth: 1 }), TOOL('sim', SIMBTN, 1800, { nth: 3 }), W(1200), TOOL('sim', SIMBTN, 1600, { nth: 3 }),
      { do: 'select', tool: 'sim', target: '.menu select, .tools select', arg: '2', ms: 1400 }, { do: 'select', tool: 'sim', target: '.menu select, .tools select', arg: '1', ms: 600 }, K('Escape', 300)] },

  { id: 'work-list', group: 'work', t: ['Work: the list', 'Lavoro: l’elenco'], covers: ['WP', 'E', 'PW', 'O'],
    c: ['One page for everything in flight. Saved views, a project filter and groups by what a mission is waiting on.', 'Una pagina per tutto ciò che è in corso. Viste salvate, filtro per progetto e gruppi per ciò che una missione aspetta.'],
    steps: [N('#/work', 900), H('att-*', 1300, { optional: true }), U, C('work-view-running', 1300), C('work-view-blocked', 1300), C('work-view-needs', 1200), C('work-p-archeus', 1400), C('work-all', 1000), C('work-view-all', 800)] },

  { id: 'work-graph', group: 'work', t: ['Work: the graph', 'Lavoro: il grafo'], covers: ['WP', 'N', 'E'],
    c: ['The same work as a graph. A view or a project dims everything else, and a node and its row light each other up.', 'Lo stesso lavoro come grafo. Una vista o un progetto attenua il resto, e un nodo e la sua riga si accendono a vicenda.'],
    steps: [N('#/work', 700), C('work-as-graph', 1500), H('wg-m-date', 1600, { optional: true }), U, C('work-view-needs', 1600), C('work-p-notes', 1600), C('work-all', 800), C('work-view-all', 800), C('work-as-list', 800)] },

  { id: 'work-inspect', group: 'work', t: ['Mission inspector', 'Ispettore della missione'], covers: ['D', 'E', 'N', 'PW', 'O', 'I'],
    c: ['A mission opens in seven tabs: Outcome, Plan, Now, Evidence, Why, Timeline and Relations, with its six-station spine on top.', 'Una missione si apre in sette schede: Esito, Piano, Adesso, Prove, Perché, Cronologia e Relazioni, con la barra a sei stazioni in alto.'],
    steps: [N('#/work', 600), C('m-m-date', 1500), C('itab-plan', 1000), C('itab-now', 1000), C('itab-evidence', 1000), C('itab-why', 1000), C('itab-timeline', 1000), C('itab-relations', 1000), K('Escape', 500),
      N('#/work/x-date-1', 1200), C('itab-checkpoints', 1000), C('itab-output', 800), K('Escape', 400)] },

  { id: 'work-approve', group: 'work', t: ['Approve or reject', 'Approva o rifiuta'], covers: ['E', 'N', 'P', 'H'],
    c: ['A decision says what, why, what Core does next and what rejecting costs. There is no undo. Deciding leaves a receipt.', 'Una decisione dice cosa, perché, cosa fa il Core dopo e cosa costa rifiutare. Non c’è annulla. Decidere lascia una ricevuta.'],
    steps: [N('#/work', 600), C(OPEN_DECISION, 1600), C('itab-policy', 1200), C('itab-decision', 900), C('#inspector .btn.decide.primary', 2400),
      C(OPEN_DECISION, 1500, { optional: true }), C('#inspector .btn.decide.danger', 1500, { optional: true }), C('confirm-yes', 2000, { optional: true })] },

  { id: 'projects', group: 'projects', t: ['Projects and worktrees', 'Progetti e worktree'], covers: ['PR', 'WP', 'QN'],
    c: ['Every project on one page, sorted by attention. Its details have tabs for missions, ideas, activity and settings; worktrees belong to a project.', 'Ogni progetto in una pagina, ordinato per attenzione. I dettagli hanno schede per missioni, idee, attività e impostazioni; i worktree appartengono a un progetto.'],
    steps: [N('#/projects', 700), C('projects-sort-recent', 900), C('projects-sort-name', 900), C('projects-sort-attention', 700), C('project-plate-prj-archeus', 1500), C('itab-missions', 1000), C('itab-ideas', 1000), C('itab-activity', 1000), C('itab-settings', 1000), C('itab-overview', 900), K('Escape', 400)] },

  { id: 'chat-page', group: 'chat', t: ['The Chat page', 'La pagina Chat'], covers: ['F', 'PW'],
    c: ['A full conversation with a scope and a mission to talk about, receipts of what Archeus did, and the context it is using.', 'Una conversazione completa con un ambito e una missione di cui parlare, le ricevute di ciò che Archeus ha fatto e il contesto che usa.'],
    steps: [N('#/chat', 800), H('msg-c-1', 1200, { optional: true }), U, C('chat-scope-page', 1400), K('Escape', 400), C('chat-mission', 1400, { optional: true }), K('Escape', 400),
      C('chat-more', 1000, { on: 'phone' }), C('chat-tab-receipts', 1500), C('chat-more', 700, { on: 'phone' }), C('chat-tab-context', 1500), Y('chat-in-page', '/status', 500), K('Enter', 1800)] },

  { id: 'replay-scrub', group: 'replay', t: ['Replay: scrub the record', 'Replay: scorri la registrazione'], covers: ['G', 'WP', 'PW'],
    c: ['What Core recorded, in order, read-only. Pick a mission, step back and forward, and open the evidence behind any step.', 'Ciò che il Core ha registrato, in ordine, in sola lettura. Scegli una missione, vai avanti e indietro, apri le prove di ogni passo.'],
    steps: [N('#/replay/m-date', 900), C('rp-mission', 1300, { optional: true }), K('Escape', 500, { optional: true }), C('rp-earlier', 700), C('rp-earlier', 700), C('rp-earlier', 700), C('rp-later', 700), C('tl-4', 1100), C('tl-7', 1500), C('rp-inspect', 2000, { on: 'phone' }), K('Escape', 500, { on: 'phone' })] },

  { id: 'replay-recovery', group: 'replay', t: ['Replay: recovery and reference', 'Replay: recupero e riferimenti'], covers: ['G', 'WP'],
    c: ['Evidence is labelled by its real strength. Recovery only proposes cards you approve; Reference says what was never recorded.', 'Le prove sono etichettate per la loro forza reale. Il recupero propone solo schede da approvare; i Riferimenti dicono cosa non è mai stato registrato.'],
    steps: [N('#/replay/m-date', 700), C('rp-mode-compact', 1200, { on: 'desktop' }), C('rp-mode-timeline', 800, { on: 'desktop' }), C('rp-detail-thinking', 1200, { on: 'desktop' }), C('rp-detail-normal', 600, { on: 'desktop' }),
      C('rp-nav-evidence', 1400), C('rp-nav-recovery', 1600), C('rp-nav-reference', 1800), C('rp-nav-events', 800)] },

  { id: 'security', group: 'pages', t: ['Security', 'Sicurezza'], covers: ['M', 'N', 'H'],
    c: ['A posture sentence, held actions you allow once or deny, project policy, boundaries and the emergency controls.', 'Una frase sulla postura, azioni trattenute da consentire una volta o negare, politica dei progetti, confini e controlli di emergenza.'],
    steps: [N('#/security', 800), H('sentence', 1200), U, C('security-nav-policy', 1300), C('security-nav-boundaries', 1300), C('security-nav-activity', 1300), C('security-nav-emergency', 1300), C('security-nav-overview', 700)] },

  { id: 'health', group: 'pages', t: ['Health', 'Stato di salute'], covers: ['M', 'N', 'H'],
    c: ['Checks and readings, filtered by what needs attention. Run a check and see its answer; unknown is never shown as fine.', 'Controlli e letture, filtrati per ciò che richiede attenzione. Esegui un controllo e vedi la risposta; sconosciuto non è mai mostrato come a posto.'],
    steps: [N('#/health', 800), C('health-nav-attention', 1200), C('health-nav-unknown', 1200), C('health-nav-ok', 1200), C('health-nav-all', 800), C('hl-run-chk-disk', 1800)] },

  { id: 'usage', group: 'pages', t: ['Usage', 'Utilizzo'], covers: ['H', 'HX', 'M'],
    c: ['Limits as numbers with their reset time, per account and per harness. A reading that is missing says unknown, never zero.', 'Limiti come numeri con l’ora di reset, per account e per harness. Una lettura mancante dice sconosciuto, mai zero.'],
    steps: [N('#/usage', 800), C('hf-codex', 1300), C('hf-all', 800), C('usage-nav-windows', 1300), C('usage-nav-history', 1300), C('usage-nav-accounts', 800)] },

  { id: 'accounts', group: 'pages', t: ['Accounts and harnesses', 'Account e harness'], covers: ['HX', 'H', 'N'],
    c: ['Claude Code, Codex and pi side by side: accounts, models, the failover order per harness and what each one starts with.', 'Claude Code, Codex e pi affiancati: account, modelli, ordine di failover per harness e con cosa parte ciascuno.'],
    steps: [N('#/accounts', 800), C('hf-claude_code', 1200), C('hf-codex', 1200), C('hf-all', 700), C('accounts-nav-models', 1300), C('accounts-nav-failover', 1300), C('accounts-nav-launch', 1300), C('accounts-nav-accounts', 700)] },

  { id: 'extensions', group: 'pages', t: ['Extensions', 'Estensioni'], covers: ['HX', 'H', 'N', 'M'],
    c: ['Hooks, MCP servers, agents, automations and paired clients, each with a switch, a details sheet and the harnesses that support it.', 'Hook, server MCP, agenti, automazioni e client abbinati, ciascuno con un interruttore, una scheda e gli harness che lo supportano.'],
    steps: [N('#/extensions', 800), C('xtab-mcp', 1100), C('xtab-agents', 1100), C('xtab-automations', 1100), C('xtab-clients', 1100), C('xtab-hooks', 900), C('hf-codex', 1100), C('hf-all', 700), C('x-au-1', 1300, { optional: true }), K('Escape', 400)] },

  { id: 'settings', group: 'pages', t: ['Settings', 'Impostazioni'], covers: ['E', 'PD', 'J'],
    c: ['Safety, Appearance, Prototype and About. Pause all, Resume all and the emergency stop live here too, and the key list opens from here.', 'Sicurezza, Aspetto, Prototipo e Informazioni. Qui ci sono anche Pausa, Riprendi e arresto d’emergenza, e da qui si apre l’elenco dei tasti.'],
    steps: [N('#/settings', 800), C('set-nav-appearance', 1200, { on: 'desktop' }), C('set-nav-prototype', 1200, { on: 'desktop' }), C('set-nav-about', 1200, { on: 'desktop' }), C('set-nav-safety', 900, { on: 'desktop' }), C('show-keys', 2200, { optional: true }), K('Escape', 400)] },

  { id: 'terminal', group: 'terminal', t: ['Terminal view', 'Vista terminale'], covers: ['O', 'J', 'I'],
    c: ['The same state as text. Number keys switch screens, j and k move, Enter opens, ? lists the keys; L, G and T change colours, glyphs and Read mode.', 'Lo stesso stato come testo. I numeri cambiano schermata, j e k si muovono, Invio apre, ? elenca i tasti; L, G e T cambiano colori, glifi e modo Lettura.'],
    steps: [N('#/terminal', 1400), K('2', 1200), K('j', 500), K('j', 500), K('Enter', 1400), K('e', 1000), K('w', 1000), K('Escape', 700), K('?', 2000), K('Escape', 500), K('g', 1300), K('Escape', 500),
      K('L', 1100), K('L', 1100), K('L', 1100), K('L', 900), K('G', 1100), K('G', 700), K('T', 1400), K('T', 700), K('1', 800)] },

  { id: 'palette', group: 'quick', t: ['Search and commands (Ctrl K)', 'Cerca e comandi (Ctrl K)'], covers: ['E', 'P', 'PA'],
    c: ['Ctrl K opens one box for pages, projects and actions. Type a few letters, press Enter, and you are there.', 'Ctrl K apre un’unica casella per pagine, progetti e azioni. Scrivi poche lettere, premi Invio e sei arrivato.'],
    steps: [N('#/now', 500), { do: 'press', arg: 'ctrl+k', target: 'document', ms: 1200 }, Y('pal-q', 'health', 1300), K('Enter', 1400)] },

  { id: 'estop', group: 'quick', t: ['Stop and re-arm', 'Ferma e riarma'], covers: ['P', 'H', 'PH'],
    c: ['Stop always asks twice. It ends every running mission, blocks new work until you re-arm, and re-arming asks again.', 'Ferma chiede sempre due volte. Termina ogni missione in corso, blocca il nuovo lavoro finché non riarmi, e riarmare chiede di nuovo.'],
    steps: [N('#/now', 500), C('safety', 1500, { on: 'desktop' }), K('Escape', 400, { on: 'desktop' }), C(STOP, 1700), C('estop-yes', 2200), C(STOP, 1500), C('rearm-yes', 2000)] },

  { id: 'notes', group: 'quick', t: ['Decision notes', 'Note sulle decisioni'], covers: ['J'],
    c: ['A dashed note under a choice names the owner decision behind it. They can be switched off for a clean view.', 'Una nota tratteggiata sotto una scelta nomina la decisione del proprietario che c’è dietro. Si possono spegnere per una vista pulita.'],
    steps: [N('#/work', 600), TOOL('theme', TOGGLE, 2200, { nth: 2 }), TOOL('theme', TOGGLE, 1200, { nth: 2 }), K('Escape', 400)] },

  { id: 'language', group: 'look', t: ['Italian and English', 'Italiano e inglese'], covers: ['J'],
    c: ['The whole interface switches to Italian and back. Mission titles stay as Core wrote them.', 'Tutta l’interfaccia passa all’italiano e ritorna. I titoli delle missioni restano come li ha scritti il Core.'],
    steps: [N('#/now', 500), TOOL('theme', TOGGLE, 2600, { nth: 1 }), TOOL('theme', TOGGLE, 1200, { nth: 1 }), K('Escape', 400)] },

  { id: 'themes', group: 'look', t: ['Six themes', 'Sei temi'], covers: ['A', 'B', 'H', 'J'],
    c: ['Dark and Light, each in standard and high contrast, plus System and a forced colours simulation. The ground is flat; state never relies on colour alone.', 'Scuro e Chiaro, ciascuno standard e ad alto contrasto, più Sistema e una simulazione dei colori forzati. Lo sfondo è piatto; lo stato non dipende mai dal solo colore.'],
    steps: [N('#/work?as=graph', 500), TOOL('theme', THEME, 1600, { nth: 1 }), TOOL('theme', THEME, 1500, { nth: 2 }), TOOL('theme', THEME, 1500, { nth: 3 }), TOOL('theme', THEME, 1500, { nth: 5 }), TOOL('theme', THEME, 1300, { nth: 4 }), TOOL('theme', THEME, 900, { nth: 0 }), K('Escape', 300), C('work-as-list', 300)] },

  { id: 'motion', group: 'look', t: ['Reduced motion', 'Movimento ridotto'], covers: ['C'],
    c: ['Quiet mode stops every loop and every glide. The core mark stands still and says how many missions run.', 'La modalità Quieta ferma ogni ciclo e ogni scorrimento. Il simbolo del nucleo sta fermo e dice quante missioni girano.'],
    steps: [N('#/now', 500), TOOL('theme', TOGGLE, 2600, { nth: 0 }), TOOL('theme', TOGGLE, 1500, { nth: 0 }), K('Escape', 400)] },

  { id: 'scale', group: 'look', t: ['Ten, thirty, a hundred projects', 'Dieci, trenta, cento progetti'], covers: ['R', 'Q', 'QN'],
    c: ['The same pages at scale: 10, 30 and 100 simulated projects, a calm story with finished work, and your own projects when this PC has them.', 'Le stesse pagine in scala: 10, 30 e 100 progetti simulati, una storia calma con il lavoro finito e i tuoi progetti se questo PC li ha.'],
    steps: [N('#/now', 400), TOOL('projects', THEME, 3000, { nth: 1 }), TOOL('projects', THEME, 3000, { nth: 3 }), TOOL('projects', THEME, 3500, { nth: 5 }),
      { do: 'reload', arg: { story: 'calm' }, ms: 3500 }, TOOL('projects', THEME, 2500, { nth: 6, optional: true }), { do: 'reload', arg: 'baseline', ms: 2000 }] },

  { id: 'devices', group: 'look', t: ['Device frames', 'Cornici dei dispositivi'], covers: ['J', 'P'],
    c: ['Tablet, desktop and Terminal frames of the same app, and All devices: four panes driven by one simulation.', 'Cornici tablet, desktop e Terminale della stessa app, e Tutti i dispositivi: quattro riquadri guidati da una sola simulazione.'],
    steps: [N('#/now', 400), TOOL('device', '[data-device="tablet"]', 2400, { on: 'desktop' }), TOOL('device', '[data-device="desktop"]', 2000, { on: 'desktop' }), TOOL('device', '[data-device="terminal"]', 2200, { on: 'desktop' }),
      TOOL('device', '[data-device="all"]', 4000, { on: 'desktop' }), TOOL('device', '[data-device="auto"]', 1200, { on: 'desktop' })] },

  { id: 'phone-bar', group: 'phone', t: ['Phone: bar and Places', 'Telefono: barra e Luoghi'], covers: ['PA', 'PH', 'J'],
    c: ['On a phone the bar holds Overview, Work, Tell, Places and Stop. Places lists every destination and your projects.', 'Su un telefono la barra ha Panoramica, Lavoro, Dimmi, Luoghi e Ferma. I Luoghi elencano ogni destinazione e i tuoi progetti.'],
    steps: [TOOL('device', '[data-device="phone"]', 2200, { on: 'desktop' }), N('#/now', 600), C('bb-work', 1200), C('bb-places', 1600), C('places-route-replay', 1600), C('bb-places', 1200), C('places-search', 1500), K('Escape', 500), K('Escape', 500)] },

  { id: 'phone-tell', group: 'phone', env: { device: 'phone' }, t: ['Phone: the Tell sheet', 'Telefono: la scheda Dimmi'], covers: ['PS', 'F'],
    c: ['Tell is a sheet you can pull up or down. The slash menu takes the place of the thread, so the composer is never pushed out.', 'Dimmi è una scheda che si tira su o giù. Il menu slash prende il posto della conversazione, così il campo non viene mai spinto fuori.'],
    steps: [N('#/now', 500), C('bb-tell', 1400), Y(SHEET_IN, '/', 1600), { do: 'clear', target: SHEET_IN, ms: 300 }, Y(SHEET_IN, '/status', 500), K('Enter', 1800), K('Escape', 600), K('Escape', 400)] },

  { id: 'phone-sheets', group: 'phone', env: { device: 'phone' }, t: ['Phone: inspector and safety sheets', 'Telefono: schede ispettore e sicurezza'], covers: ['PS', 'PH', 'PA'],
    c: ['An inspector is a sheet over the page. Stop on the bar arms a two step stop; the confirm sits away from the thumb.', 'Un ispettore è una scheda sopra la pagina. Ferma nella barra arma un arresto in due passi; la conferma sta lontano dal pollice.'],
    steps: [N('#/projects/prj-archeus', 1800), C('itab-missions', 1000), K('Escape', 700), N('#/now', 500), C('bb-stop', 2000), K('Escape', 600)] },

  { id: 'phone-replay', group: 'phone', env: { device: 'phone' }, t: ['Phone: Replay', 'Telefono: Replay'], covers: ['PD', 'G'],
    c: ['Replay on a phone shows one section at a time. Evidence opens as a sheet, and one button sets the layout and the detail.', 'Replay su un telefono mostra una sezione alla volta. Le prove si aprono in una scheda e un pulsante imposta layout e dettaglio.'],
    steps: [N('#/replay/m-date', 900), C('rp-view', 1400, { optional: true }), K('Escape', 500), C('tl-4', 1500), C('rp-inspect', 1600, { optional: true }), K('Escape', 500), C('rp-nav-recovery', 1300), C('rp-nav-reference', 1300), C('rp-nav-events', 600)] },

  { id: 'phone-pages', group: 'phone', env: { device: 'phone' }, t: ['Phone: the other pages', 'Telefono: le altre pagine'], covers: ['PD', 'PS', 'PA'],
    c: ['Security, Health, Accounts and Settings share one phone head. Pickers are lists in a sheet, and the terminal keeps a Places and Stop row.', 'Sicurezza, Salute, Account e Impostazioni condividono una testata da telefono. I selettori sono elenchi in una scheda e il terminale ha una riga Luoghi e Ferma.'],
    steps: [N('#/security', 1400), N('#/health', 1300), N('#/accounts', 1300), N('#/settings', 1300), N('#/chat', 800), C('chat-scope-page', 1600), K('Escape', 500), N('#/terminal', 1600), N('#/now', 500),
      TOOL('device', '[data-device="auto"]', 1200, { on: 'desktop' })] }
];

export const familiesCovered = () => new Set(CHAPTERS.flatMap((c) => c.covers));
