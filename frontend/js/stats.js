// Persistent daily-challenge stats in localStorage (no accounts, per-device).

const STATS_KEY = "mastermind_stats";
// Matches the backend DAILY_EPOCH (2024-01-01 UTC = puzzle #1).
const DAILY_EPOCH_UTC = Date.UTC(2024, 0, 1);

function todayDailyNumber() {
	return Math.floor((Date.now() - DAILY_EPOCH_UTC) / 86400000) + 1;
}

function _emptyStats() {
	return { gamesPlayed: 0, wins: 0, currentStreak: 0, maxStreak: 0, lastDailyDay: null, guessDist: {} };
}

function _loadStats() {
	try {
		return JSON.parse(localStorage.getItem(STATS_KEY)) || _emptyStats();
	} catch {
		return _emptyStats();
	}
}

function _saveStats(s) {
	localStorage.setItem(STATS_KEY, JSON.stringify(s));
}

function getStats() {
	return _loadStats();
}

function hasPlayedDaily(day) {
	return _loadStats().lastDailyDay === day;
}

// Fold one finished daily game into the saved stats. Idempotent per day.
function recordDaily({ day, solved, guesses }) {
	const s = _loadStats();
	if (s.lastDailyDay === day) return s;
	s.gamesPlayed += 1;
	if (solved) {
		s.wins += 1;
		s.currentStreak = s.lastDailyDay === day - 1 ? s.currentStreak + 1 : 1;
		s.maxStreak = Math.max(s.maxStreak, s.currentStreak);
		s.guessDist[guesses] = (s.guessDist[guesses] || 0) + 1;
	} else {
		s.currentStreak = 0;
	}
	s.lastDailyDay = day;
	_saveStats(s);
	return s;
}
