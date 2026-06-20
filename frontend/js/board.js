// Rendering helpers for pegs, guess history, feedback, and the guess editor.

function pegEl(colorIndex) {
	const peg = document.createElement("span");
	peg.className = "peg";
	if (colorIndex === null || colorIndex === undefined) {
		peg.classList.add("peg--empty");
		return peg;
	}
	const c = PALETTE[colorIndex];
	peg.style.background = c.bg;
	peg.textContent = c.symbol;
	peg.setAttribute("aria-label", `color ${colorIndex + 1}`);
	return peg;
}

// Black = right color & position, white = right color wrong position.
function feedbackEl(black, white, codeLength) {
	const wrap = document.createElement("span");
	wrap.className = "feedback";
	for (let i = 0; i < black; i++) wrap.appendChild(keyPeg("black"));
	for (let i = 0; i < white; i++) wrap.appendChild(keyPeg("white"));
	const blanks = codeLength - black - white;
	for (let i = 0; i < blanks; i++) wrap.appendChild(keyPeg("none"));
	return wrap;
}

function keyPeg(kind) {
	const k = document.createElement("span");
	k.className = `key key--${kind}`;
	return k;
}

function guessRow(result, codeLength) {
	const row = document.createElement("div");
	row.className = "guess-row";
	const pegs = document.createElement("div");
	pegs.className = "pegs";
	for (const c of result.guess) pegs.appendChild(pegEl(c));
	row.appendChild(pegs);
	row.appendChild(feedbackEl(result.black, result.white, codeLength));
	return row;
}

// Render a player's full guess history into `container`.
function renderHistory(container, board, codeLength) {
	container.innerHTML = "";
	for (const result of board) container.appendChild(guessRow(result, codeLength));
	container.scrollTop = container.scrollHeight;
}

// Interactive editor for composing one guess. `onSubmit(guess)` fires when the
// player confirms a full row. Returns a controller with a `reset()` method.
function createGuessEditor(container, codeLength, nColors, onSubmit, submitLabel = "Submit guess") {
	container.innerHTML = "";
	let slots = new Array(codeLength).fill(null);
	let _enabled = true;

	const row = document.createElement("div");
	row.className = "editor-row";

	const slotEls = [];
	const slotsWrap = document.createElement("div");
	slotsWrap.className = "pegs";
	for (let i = 0; i < codeLength; i++) {
		const s = pegEl(null);
		s.classList.add("slot");
		s.title = "Click to clear";
		s.addEventListener("click", () => {
			if (!_enabled) return;
			slots[i] = null;
			refresh();
		});
		slotEls.push(s);
		slotsWrap.appendChild(s);
	}
	row.appendChild(slotsWrap);

	const palette = document.createElement("div");
	palette.className = "palette";
	for (let c = 0; c < nColors; c++) {
		const btn = pegEl(c);
		btn.classList.add("palette-btn");
		btn.setAttribute("role", "button");
		btn.addEventListener("click", () => {
			const idx = slots.indexOf(null);
			if (idx !== -1) {
				slots[idx] = c;
				refresh();
			}
		});
		palette.appendChild(btn);
	}

	const submit = document.createElement("button");
	submit.className = "btn btn--primary submit-guess";
	submit.textContent = submitLabel;
	submit.addEventListener("click", () => {
		if (slots.includes(null)) return;
		onSubmit(slots.slice());
	});

	container.appendChild(row);
	container.appendChild(palette);
	container.appendChild(submit);

	function refresh() {
		for (let i = 0; i < codeLength; i++) {
			const fresh = pegEl(slots[i]);
			fresh.classList.add("slot");
			fresh.addEventListener("click", () => {
				if (!_enabled) return;
				slots[i] = null;
				refresh();
			});
			slotEls[i].replaceWith(fresh);
			slotEls[i] = fresh;
		}
		submit.disabled = !_enabled || slots.includes(null);
	}

	refresh();
	return {
		reset() {
			slots = new Array(codeLength).fill(null);
			refresh();
		},
		setEnabled(on) {
			_enabled = on;
			submit.disabled = !on || slots.includes(null);
			palette.classList.toggle("disabled", !on);
			slotsWrap.style.opacity = on ? "" : "0.5";
		},
	};
}
