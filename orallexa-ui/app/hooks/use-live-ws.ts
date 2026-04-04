"use client";

import { useEffect, useRef, useCallback, useState } from "react";

/**
 * WebSocket hook for real-time price + signal updates.
 *
 * Connects to /ws/live, auto-reconnects with exponential backoff,
 * falls back to HTTP polling if WebSocket unavailable.
 *
 * Usage:
 *   const { livePrice, isConnected } = useLiveWS(apiUrl, ticker, autoRefresh);
 */

interface LivePrice {
  price: number;
  change_pct: number;
  prev_close: number;
  high: number;
  low: number;
  timestamp: string;
}

interface SignalEvent {
  ticker: string;
  decision: string;
  confidence: number;
  risk_level: string;
}

interface UseLiveWSReturn {
  livePrice: LivePrice | null;
  signal: SignalEvent | null;
  isConnected: boolean;
  priceFlash: "up" | "down" | null;
}

const MAX_RECONNECT_DELAY = 30000;
const INITIAL_RECONNECT_DELAY = 1000;

export function useLiveWS(
  apiUrl: string,
  ticker: string,
  enabled: boolean = true,
): UseLiveWSReturn {
  const [livePrice, setLivePrice] = useState<LivePrice | null>(null);
  const [signal, setSignal] = useState<SignalEvent | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [priceFlash, setPriceFlash] = useState<"up" | "down" | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectDelay = useRef(INITIAL_RECONNECT_DELAY);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevPrice = useRef<number | null>(null);

  const connect = useCallback(() => {
    if (!enabled || !ticker) return;

    // Build WS URL from API URL
    const wsUrl = apiUrl.replace(/^http/, "ws").replace(/\/+$/, "") + "/ws/live";

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        reconnectDelay.current = INITIAL_RECONNECT_DELAY;
        // Subscribe to ticker
        ws.send(JSON.stringify({ type: "subscribe", ticker }));
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.event === "price" && data.ticker === ticker) {
            const newPrice: LivePrice = {
              price: data.price,
              change_pct: data.change_pct ?? 0,
              prev_close: data.prev_close ?? 0,
              high: data.high ?? data.price,
              low: data.low ?? data.price,
              timestamp: data.timestamp ?? new Date().toISOString(),
            };

            // Flash animation
            if (prevPrice.current !== null && data.price !== prevPrice.current) {
              setPriceFlash(data.price > prevPrice.current ? "up" : "down");
              setTimeout(() => setPriceFlash(null), 800);
            }
            prevPrice.current = data.price;
            setLivePrice(newPrice);
          }

          if (data.event === "signal" && data.ticker === ticker) {
            setSignal({
              ticker: data.ticker,
              decision: data.decision,
              confidence: data.confidence,
              risk_level: data.risk_level,
            });
          }
        } catch { /* ignore malformed messages */ }
      };

      ws.onclose = () => {
        setIsConnected(false);
        wsRef.current = null;
        // Auto-reconnect with exponential backoff
        if (enabled) {
          reconnectTimer.current = setTimeout(() => {
            reconnectDelay.current = Math.min(
              reconnectDelay.current * 2,
              MAX_RECONNECT_DELAY,
            );
            connect();
          }, reconnectDelay.current);
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      // WebSocket not available, stay disconnected (page.tsx falls back to polling)
      setIsConnected(false);
    }
  }, [apiUrl, ticker, enabled]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  // Re-subscribe when ticker changes
  useEffect(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN && ticker) {
      wsRef.current.send(JSON.stringify({ type: "subscribe", ticker }));
      prevPrice.current = null;
    }
  }, [ticker]);

  return { livePrice, signal, isConnected, priceFlash };
}
