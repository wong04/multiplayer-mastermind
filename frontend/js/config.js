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
	{ bg: "#e6483d", symbol: "●" }, // red, circle
	{ bg: "#2d8cf0", symbol: "■" }, // blue, square
	{ bg: "#19be6b", symbol: "▲" }, // green, triangle
	{ bg: "#f7b500", symbol: "★" }, // yellow, star
	{ bg: "#9b59b6", symbol: "◆" }, // purple, diamond
	{ bg: "#ff7a18", symbol: "✦" }, // orange, sparkle
	{ bg: "#00bcd4", symbol: "▭" }, // cyan, bar
	{ bg: "#e91e8c", symbol: "♥" }, // pink, heart
	{ bg: "#7f8c8d", symbol: "▬" }, // grey, rect
	{ bg: "#34495e", symbol: "❖" }, // navy, lozenge
];
