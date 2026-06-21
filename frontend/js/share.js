// Build a shareable emoji grid from a daily game's per-slot feedback.

const SHARE_EMOJI = { exact: "🟩", present: "🟨", absent: "⬛" };

function buildShareGrid(dailyNo, board, maxGuesses, solved) {
	const score = solved ? board.length : "X";
	const lines = [`Mastermind Daily #${dailyNo}  ${score}/${maxGuesses}`];
	for (const row of board) {
		const fb = row.per_slot && row.per_slot.length ? row.per_slot : [];
		lines.push(fb.map((s) => SHARE_EMOJI[s] || "⬛").join(""));
	}
	return lines.join("\n");
}
