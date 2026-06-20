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

// Positional feedback: each square corresponds to the peg in the same slot.
// per_slot is an array of "exact" | "present" | "absent".
function feedbackEl(perSlot) {
	const wrap = document.createElement("span");
	wrap.className = "feedback";
	const kindMap = { exact: "black", present: "white", absent: "none" };
	for (const s of perSlot) wrap.appendChild(keyPeg(kindMap[s] || "none"));
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
	// per_slot gives positional feedback; fall back to count-based for old data
	const perSlot = result.per_slot && result.per_slot.length === codeLength
		? result.per_slot
		: [
			...Array(result.black).fill("exact"),
			...Array(result.white).fill("present"),
			...Array(codeLength - result.black - result.white).fill("absent"),
		  ];
	row.appendChild(feedbackEl(perSlot));
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
