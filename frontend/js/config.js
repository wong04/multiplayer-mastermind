// Backend WebSocket endpoint.
//
// Local dev points at the FastAPI server on :8000. In production, set
// PROD_WS_URL to your Railway URL, e.g. "wss://your-app.up.railway.app/ws".
const PROD_WS_URL = "wss://multiplayer-mastermind-production.up.railway.app/ws";

function backendWsUrl() {
	const host = window.location.hostname;
	if (host === "localhost" || host === "127.0.0.1" || host === "") {
		return "ws://localhost:8000/ws";
	}
	return PROD_WS_URL;
}

// Palette: distinct hues, each paired with a symbol so colorblind players can
// still tell them apart. Supports configs up to 10 colors.
const PALETTE = [
	{ bg: "#ff2222", symbol: "●" }, // NES red
	{ bg: "#0088ff", symbol: "■" }, // NES blue
	{ bg: "#33ff66", symbol: "▲" }, // phosphor green
	{ bg: "#ffcc00", symbol: "★" }, // NES yellow
	{ bg: "#cc44ff", symbol: "◆" }, // NES purple
	{ bg: "#ff8800", symbol: "✦" }, // NES orange
	{ bg: "#00ffee", symbol: "▭" }, // cyan
	{ bg: "#ff44aa", symbol: "♥" }, // hot pink
	{ bg: "#888888", symbol: "▬" }, // grey
	{ bg: "#4488cc", symbol: "❖" }, // steel blue
];
