// Visual FX: CRT boot sequence, power-on, and typewriter text.
// Purely cosmetic — never touches game state or any element the game logic reads.

(function () {
	const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

	const wait = (ms) => new Promise((r) => setTimeout(r, ms));

	// Type `text` into `el`, appending. Resolves when done or when shouldSkip() is true.
	function typeInto(el, text, speed, shouldSkip) {
		return new Promise((resolve) => {
			let i = 0;
			const step = () => {
				if (shouldSkip && shouldSkip()) {
					el.textContent += text.slice(i);
					return resolve();
				}
				if (i >= text.length) return resolve();
				el.textContent += text[i++];
				setTimeout(step, speed);
			};
			step();
		});
	}

	async function typeTagline() {
		const h2 = document.querySelector("#screen-home h2");
		if (!h2) return;
		const full = h2.textContent;
		if (REDUCED) {
			h2.innerHTML = `${full}<span class="caret"></span>`;
			return;
		}
		h2.textContent = "";
		await typeInto(h2, full, 28, null);
		const caret = document.createElement("span");
		caret.className = "caret";
		h2.appendChild(caret);
	}

	async function powerOff(boot) {
		boot.classList.add("boot--off");
		await wait(650);
		boot.remove();
	}

	async function runBoot() {
		const boot = document.getElementById("boot");
		const log = document.getElementById("boot-log");
		if (!boot) return;

		// Reduced motion: no flash, no delay — straight to the app.
		if (REDUCED) {
			boot.remove();
			typeTagline();
			return;
		}

		const lines = [
			"MASTERMIND CIPHER TERMINAL  v4.8",
			"",
			"booting cipher_core ........... OK",
			"loading palette ............... OK",
			"calibrating phosphor .......... OK",
			"sync handshake ................ OK",
			"",
			"> awaiting operator_",
		];

		let skipped = false;
		const skip = () => { skipped = true; };
		window.addEventListener("click", skip, { once: true });
		window.addEventListener("keydown", skip, { once: true });

		for (const line of lines) {
			await typeInto(log, line + "\n", 14, () => skipped);
			if (!skipped) await wait(90);
		}

		window.removeEventListener("click", skip);
		window.removeEventListener("keydown", skip);

		await wait(skipped ? 120 : 420);
		await powerOff(boot);
		typeTagline();
	}

	// Never let a cosmetic failure trap the app behind the boot overlay.
	async function safeBoot() {
		try {
			await runBoot();
		} catch (e) {
			const boot = document.getElementById("boot");
			if (boot) boot.remove();
		}
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", safeBoot);
	} else {
		safeBoot();
	}
})();
