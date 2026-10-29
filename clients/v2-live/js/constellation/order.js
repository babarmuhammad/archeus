import {stateKey} from './geometry.js';

// How projects and their missions are ordered where they are listed or first placed: what needs you first, then what runs, then the most recent.
const RANK = {'needs-you': 5, running: 4, blocked: 3, paused: 2, thinking: 2, done: 1, idle: 0};
const priorityOf = p => (p.attention ? 2 : p.running ? 1 : 0);
export const orderProjects = projects => [...projects].sort((a, b) => priorityOf(b) - priorityOf(a) || (b.lastAt || 0) - (a.lastAt || 0) || String(a.id).localeCompare(String(b.id)));
export const leadMission = p => [...p.missions].sort((a, b) => RANK[stateKey(b.state)] - RANK[stateKey(a.state)] || (b.at || 0) - (a.at || 0) || String(a.id).localeCompare(String(b.id)))[0] || null;
