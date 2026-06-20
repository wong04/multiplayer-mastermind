// Thin WebSocket wrapper: JSON messaging, type-based dispatch, and
// auto-reconnect that replays a stored session token.
class GameSocket {
	constructor(url) {
		this.url = url;
		this.handlers = {};
		this.onStatus = () => {};
		this.ws = null;
		this._queue = [];
		this._reconnectDelay = 500;
		this._intentionalClose = false;
		// Called right after the socket (re)opens, e.g. to send a reconnect.
		this.onOpen = () => {};
	}

	on(type, fn) {
		this.handlers[type] = fn;
	}

	connect() {
		this._intentionalClose = false;
		this.onStatus("connecting");
		this.ws = new WebSocket(this.url);

		this.ws.onopen = () => {
			this._reconnectDelay = 500;
			this.onStatus("online");
			this.onOpen();
			for (const msg of this._queue.splice(0)) this._raw(msg);
		};

		this.ws.onmessage = (ev) => {
			let msg;
			try {
				msg = JSON.parse(ev.data);
			} catch {
				return;
			}
			const fn = this.handlers[msg.type];
			if (fn) fn(msg);
		};

		this.ws.onclose = () => {
			if (this._intentionalClose) return;
			this.onStatus("offline");
			this._reconnectDelay = Math.min(this._reconnectDelay * 2, 8000);
			setTimeout(() => this.connect(), this._reconnectDelay);
		};

		this.ws.onerror = () => this.ws && this.ws.close();
	}

	send(obj) {
		if (this.ws && this.ws.readyState === WebSocket.OPEN) {
			this._raw(obj);
		} else {
			this._queue.push(obj);
		}
	}

	_raw(obj) {
		this.ws.send(JSON.stringify(obj));
	}

	close() {
		this._intentionalClose = true;
		if (this.ws) this.ws.close();
	}
}
