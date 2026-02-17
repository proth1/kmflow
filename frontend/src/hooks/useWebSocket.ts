/**
 * WebSocket connection hook for real-time monitoring data.
 *
 * Manages WebSocket lifecycle, automatic reconnection,
 * and heartbeat handling.
 */

import { useCallback, useEffect, useRef, useState } from "react";

const WS_BASE_URL =
  process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

export interface WebSocketMessage {
  event_type?: string;
  type?: string;
  [key: string]: unknown;
}

export interface UseWebSocketOptions {
  onMessage?: (msg: WebSocketMessage) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  reconnectInterval?: number;
  maxRetries?: number;
}

export interface UseWebSocketReturn {
  isConnected: boolean;
  lastMessage: WebSocketMessage | null;
  sendMessage: (data: string) => void;
  disconnect: () => void;
}

export function useWebSocket(
  path: string,
  options: UseWebSocketOptions = {},
): UseWebSocketReturn {
  const {
    onMessage,
    onConnect,
    onDisconnect,
    reconnectInterval = 5000,
    maxRetries = 10,
  } = options;

  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const url = `${WS_BASE_URL}${path}`;
    const ws = new WebSocket(url);

    ws.onopen = () => {
      setIsConnected(true);
      retriesRef.current = 0;
      onConnect?.();
    };

    ws.onmessage = (event) => {
      try {
        const data: WebSocketMessage = JSON.parse(event.data);
        if (data.type === "heartbeat") {
          ws.send("ping");
          return;
        }
        setLastMessage(data);
        onMessage?.(data);
      } catch {
        // Non-JSON messages (like "pong") are ignored
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      onDisconnect?.();
      // Auto-reconnect
      if (retriesRef.current < maxRetries) {
        retriesRef.current += 1;
        reconnectTimerRef.current = setTimeout(connect, reconnectInterval);
      }
    };

    ws.onerror = () => {
      ws.close();
    };

    wsRef.current = ws;
  }, [path, onMessage, onConnect, onDisconnect, reconnectInterval, maxRetries]);

  const sendMessage = useCallback((data: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(data);
    }
  }, []);

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
    }
    retriesRef.current = maxRetries; // Prevent reconnect
    wsRef.current?.close();
  }, [maxRetries]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      retriesRef.current = maxRetries;
      wsRef.current?.close();
    };
  }, [connect, maxRetries]);

  return { isConnected, lastMessage, sendMessage, disconnect };
}
