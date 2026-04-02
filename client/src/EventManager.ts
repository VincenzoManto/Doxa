// Handles different types of events from the WebSocket
export type DoxaEvent = {
  type: string;
  [key: string]: any;
};

export class EventManager {
  private handlers: Record<string, ((event: DoxaEvent) => void)[]> = {};

  // Register a handler for a specific event type
  on(type: string, handler: (event: DoxaEvent) => void) {
    if (!this.handlers[type]) this.handlers[type] = [];
    this.handlers[type].push(handler);
  }

  // Remove a handler for a specific event type
  off(type: string, handler: (event: DoxaEvent) => void) {
    if (!this.handlers[type]) return;
    this.handlers[type] = this.handlers[type].filter(h => h !== handler);
  }

  // Handle an incoming event (dispatch to all handlers for its type)
  handle(event: DoxaEvent) {
    const { type } = event;
    if (this.handlers[type]) {
      this.handlers[type].forEach(handler => handler(event));
    }
    if (this.handlers['*']) {
      this.handlers['*'].forEach(handler => handler(event));
    }
  }
}
