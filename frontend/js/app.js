// Main client controller: connection, screen routing, and rendering.

const SESSION_KEY = "mastermind_session";

const S = {
	playerId: null,
	playerToken: null,
	roomCode: null,
	hostId: null,
	mode: "classic",
	config: null,
	players: [],
	round: null,
	editor: null,
};

const socket = new GameSocket(backendWsUrl());

// -- helpers ---------------------------------------------------------------

const $ = (id) => document.getElementById(id);

function showScreen(name) {
	for (const el of document.querySelectorAll(".screen")) {
		el.classList.toggle("active", el.id === `screen-${name}`);
	}
}

function isHost() {
	return S.playerId && S.playerId === S.hostId;
}

function nameOf(playerId) {
	const p = S.players.find((x) => x.id === playerId);
	return p ? p.nickname : "someone";
}

function saveSession() {
	if (S.roomCode && S.playerToken) {
		localStorage.setItem(SESSION_KEY, JSON.stringify({ roomCode: S.roomCode, token: S.playerToken }));
	}
}

function clearSession() {
	localStorage.removeItem(SESSION_KEY);
}

function toast(message, kind = "info") {
	const t = $("toast");
	t.textContent = message;
	t.className = `toast toast--${kind} show`;
	clearTimeout(toast._timer);
	toast._timer = setTimeout(() => t.classList.remove("show"), 3000);
}

// -- connection status -----------------------------------------------------

socket.onStatus = (status) => {
	const dot = $("status-dot");
	dot.className = `status-dot status-dot--${status}`;
	$("status-text").textContent = status;
};

socket.onOpen = () => {
	// On (re)connect, replay a stored session if we have one.
	const raw = localStorage.getItem(SESSION_KEY);
	if (raw && !S.playerId) {
		const sess = JSON.parse(raw);
		socket.send({ type: "reconnect", room_code: sess.roomCode, token: sess.token });
	}
};

// -- server message handlers ----------------------------------------------

socket.on("room_joined", (m) => {
	S.playerId = m.player_id;
	S.playerToken = m.player_token;
	S.roomCode = m.room_code;
	S.hostId = m.host_id;
	saveSession();
});

socket.on("lobby_update", (m) => {
	S.roomCode = m.code;
	S.hostId = m.host_id;
	S.mode = m.mode;
	S.config = m.config;
	S.players = m.players;
	if (m.state === "lobby") {
		S.round = null;
		renderLobby();
		showScreen("lobby");
	} else {
		renderScoreboards();
	}
});

socket.on("round_start", (m) => {
	S.mode = m.mode;
	S.config = m.config;
	if (m.scoreboard) S.players = m.scoreboard;
	S.round = {
		mode: m.mode,
		roundNo: m.round_no,
		role: m.role || null,
		codemakerId: m.codemaker_id || null,
		secretSet: !!m.secret_set,
		guessNo: m.guess_no || 1,
		board: m.your_board || [],
		submitted: m.submitted || 0,
		total: m.total || S.players.length,
		alreadySubmitted: !!m.already_submitted,
		ended: false,
	};
	renderGame();
	showScreen("game");
});

socket.on("guess_feedback", (m) => {
	if (!S.round) return;
	S.round.board = m.board;
	renderHistory($("history"), S.round.board, S.config.code_length);
	if (S.mode === "competition") {
		// Barrier resolved: a new guess round begins (unless round_over follows).
		S.round.alreadySubmitted = false;
		if (S.editor) {
			S.editor.reset();
			S.editor.setEnabled(true);
		}
		setStatus("");
	} else if (!m.result.solved && S.editor) {
		S.editor.reset();
		S.editor.setEnabled(true);
	}
});

socket.on("barrier_update", (m) => {
	if (!S.round) return;
	S.round.guessNo = m.guess_no;
	S.round.submitted = m.submitted;
	S.round.total = m.total;
	updateBarrierText();
});

socket.on("round_over", (m) => {
	if (S.round) S.round.ended = true;
	if (m.scoreboard) S.players = m.scoreboard;
	renderOver(m, false);
	showScreen("over");
});

socket.on("game_over", (m) => {
	if (m.scoreboard) S.players = m.scoreboard;
	renderOver(m, true);
	showScreen("over");
});

socket.on("error", (m) => toast(m.message, "error"));

// -- home screen -----------------------------------------------------------

function selectedMode() {
	const checked = document.querySelector('input[name="mode"]:checked');
	return checked ? checked.value : "classic";
}

$("btn-create").addEventListener("click", () => {
	const nickname = $("nickname").value.trim();
	if (!nickname) return toast("Enter a nickname first", "error");
	socket.send({ type: "create_room", nickname, mode: selectedMode() });
});

$("btn-join").addEventListener("click", () => {
	const nickname = $("nickname").value.trim();
	const code = $("join-code").value.trim().toUpperCase();
	if (!nickname) return toast("Enter a nickname first", "error");
	if (!code) return toast("Enter a room code", "error");
	socket.send({ type: "join_room", nickname, room_code: code });
});

// -- lobby -----------------------------------------------------------------

function renderLobby() {
	$("lobby-code").textContent = S.roomCode;
	const list = $("lobby-players");
	list.innerHTML = "";
	for (const pl of S.players) {
		const li = document.createElement("li");
		li.textContent = pl.nickname + (pl.id === S.hostId ? " (host)" : "");
		if (pl.id === S.playerId) li.classList.add("you");
		if (!pl.connected) li.classList.add("offline");
		list.appendChild(li);
	}

	$("lobby-mode-label").textContent = S.mode === "classic" ? "Classic" : "Competition";
	const host = isHost();
	$("host-controls").classList.toggle("hidden", !host);
	$("lobby-wait").classList.toggle("hidden", host);

	if (host) {
		for (const btn of document.querySelectorAll(".mode-btn")) {
			btn.classList.toggle("selected", btn.dataset.mode === S.mode);
		}
		$("cfg-length").value = S.config.code_length;
		$("cfg-colors").value = S.config.n_colors;
		$("cfg-guesses").value = S.config.max_guesses;
		$("cfg-target").value = S.config.target_score;
		$("btn-start").disabled = S.players.length < 2;
		$("start-hint").textContent = S.players.length < 2 ? "Need at least 2 players" : "";
	}
}

for (const btn of document.querySelectorAll(".mode-btn")) {
	btn.addEventListener("click", () => socket.send({ type: "set_mode", mode: btn.dataset.mode }));
}

$("btn-apply-config").addEventListener("click", () => {
	socket.send({
		type: "set_config",
		code_length: Number($("cfg-length").value),
		n_colors: Number($("cfg-colors").value),
		max_guesses: Number($("cfg-guesses").value),
		target_score: Number($("cfg-target").value),
	});
	toast("Settings applied", "info");
});

$("btn-start").addEventListener("click", () => socket.send({ type: "start_game" }));

$("btn-copy-code").addEventListener("click", () => {
	navigator.clipboard?.writeText(S.roomCode);
	toast("Room code copied", "info");
});

// -- game ------------------------------------------------------------------

function renderScoreboards() {
	for (const elId of ["game-scoreboard", "over-scoreboard"]) {
		const el = $(elId);
		if (!el) continue;
		el.innerHTML = "";
		const sorted = [...S.players].sort((a, b) => b.score - a.score);
		for (const pl of sorted) {
			const chip = document.createElement("div");
			chip.className = "score-chip";
			if (pl.id === S.playerId) chip.classList.add("you");
			if (!pl.connected) chip.classList.add("offline");
			chip.innerHTML = `<span class="sc-name">${escapeHtml(pl.nickname)}</span><span class="sc-pts">${pl.score}</span>`;
			el.appendChild(chip);
		}
	}
}

function renderGame() {
	renderScoreboards();
	const r = S.round;
	$("round-no").textContent = `Round ${r.roundNo}`;
	$("game-mode").textContent = r.mode === "classic" ? "Classic" : "Competition";

	const area = $("game-area");
	area.innerHTML = gameAreaTemplate();

	if (r.mode === "classic" && r.role === "codemaker") {
		renderCodemaker();
	} else {
		renderBreaker();
	}
}

function gameAreaTemplate() {
	return `
		<div id="status-line" class="status-line"></div>
		<div id="history" class="history"></div>
		<div id="editor" class="editor"></div>`;
}

function renderCodemaker() {
	const r = S.round;
	$("history").classList.add("hidden");
	if (!r.secretSet) {
		setStatus("You are the codemaker — pick a secret code for the others to crack.");
		S.editor = createGuessEditor(
			$("editor"),
			S.config.code_length,
			S.config.n_colors,
			(secret) => socket.send({ type: "set_secret", secret }),
			"Lock in secret",
		);
	} else {
		$("editor").innerHTML = "";
		setStatus("Secret locked in. The others are racing to crack it — sit tight!");
	}
}

function renderBreaker() {
	const r = S.round;
	$("history").classList.remove("hidden");
	renderHistory($("history"), r.board, S.config.code_length);

	if (r.mode === "classic" && !r.secretSet) {
		$("editor").innerHTML = "";
		setStatus(`Waiting for ${nameOf(r.codemakerId)} to set the secret…`);
		return;
	}

	S.editor = createGuessEditor(
		$("editor"),
		S.config.code_length,
		S.config.n_colors,
		(guess) => submitGuess(guess),
	);

	if (r.mode === "competition") {
		if (r.alreadySubmitted) {
			S.editor.setEnabled(false);
			setStatus("");
		}
		updateBarrierText();
	} else {
		setStatus("Crack the code! First to guess it wins the round.");
	}
}

function submitGuess(guess) {
	socket.send({ type: "submit_guess", guess });
	if (S.mode === "competition") {
		S.round.alreadySubmitted = true;
		S.editor.setEnabled(false);
	}
}

function setStatus(text) {
	const el = $("status-line");
	if (el) el.textContent = text;
}

function updateBarrierText() {
	if (!S.round || S.mode !== "competition") return;
	const r = S.round;
	const waiting = r.alreadySubmitted ? "Waiting for the others — " : "";
	setStatus(`${waiting}guess ${r.guessNo} · ${r.submitted}/${r.total} submitted`);
}

// -- round / game over -----------------------------------------------------

function renderOver(m, isGameOver) {
	renderScoreboards();
	const title = $("over-title");
	const sub = $("over-secret");

	if (isGameOver) {
		const champ = nameOf(m.winner_id);
		title.textContent = m.winner_id === S.playerId ? "🏆 You won the match!" : `🏆 ${champ} wins the match!`;
		sub.textContent = "";
	} else if (m.reason === "aborted") {
		title.textContent = "Round aborted (a player left)";
		sub.textContent = "";
	} else if (!m.winner_id) {
		title.textContent = "Nobody cracked it!";
		sub.appendChild(secretReveal(m.secret));
	} else {
		const who = m.winner_id === S.playerId ? "You" : nameOf(m.winner_id);
		title.textContent = m.reason === "unbroken" ? `${who} (codemaker) scored — unbroken!` : `${who} cracked the code!`;
		if (m.secret) {
			sub.innerHTML = "The code was: ";
			sub.appendChild(secretReveal(m.secret));
		}
	}

	const host = isHost();
	$("btn-next-round").classList.toggle("hidden", isGameOver || !host);
	$("btn-rematch").classList.toggle("hidden", !isGameOver || !host);
	$("over-wait").classList.toggle("hidden", host);
}

function secretReveal(secret) {
	const wrap = document.createElement("span");
	wrap.className = "pegs inline";
	for (const c of secret) wrap.appendChild(pegEl(c));
	return wrap;
}

$("btn-next-round").addEventListener("click", () => socket.send({ type: "next_round" }));
$("btn-rematch").addEventListener("click", () => socket.send({ type: "rematch" }));

$("btn-leave").addEventListener("click", () => {
	clearSession();
	location.reload();
});

function escapeHtml(s) {
	return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// -- boot ------------------------------------------------------------------

socket.connect();
showScreen("home");
