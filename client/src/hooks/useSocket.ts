import { useEffect, useState, useCallback } from 'react';
import { io, Socket } from 'socket.io-client';

const SOCKET_URL = '/';

export const useSocket = () => {
  const [socket, setSocket] = useState<Socket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [status, setStatus] = useState('Disconnected');

  useEffect(() => {
    const s = io(SOCKET_URL);

    s.on('connect', () => {
      setIsConnected(true);
      setStatus('Connected');
    });

    s.on('disconnect', () => {
      setIsConnected(false);
      setStatus('Disconnected');
    });

    s.on('status', (data: any) => {
      console.log('Server status:', data);
    });

    setSocket(s);

    return () => {
      s.disconnect();
    };
  }, []);

  const emit = useCallback((event: string, data: any) => {
    socket?.emit(event, data);
  }, [socket]);

  return { socket, isConnected, status, emit };
};
