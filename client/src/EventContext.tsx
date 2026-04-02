import React, { createContext, useContext, useState, useEffect } from 'react';
import { connectEvents } from './api';

const EventContext = createContext<any>(null);

export function useEventLog() {
  return useContext(EventContext);
}

export function EventProvider({ children }: { children: React.ReactNode }) {
  const [events, setEvents] = useState<any[]>([]);

  useEffect(() => {
    const ws = connectEvents((event) => {
      setEvents((prev) => [event, ...prev].slice(0, 100));
    });
    return () => ws.close();
  }, []);

  return (
    <EventContext.Provider value={{ events, setEvents }}>
      {children}
    </EventContext.Provider>
  );
}
