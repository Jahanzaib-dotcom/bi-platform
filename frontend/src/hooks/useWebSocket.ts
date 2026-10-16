'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { useAuthStore } from '@/store';
import { useDiscoveryStore, useSystemStore, useUIStore } from '@/store';
import type {
  WSMessage,
  WSMessageType,
  WSDiscoveryProgress,
  WSAuditProgress,
  WSSystemStats,
  WSLiveMetrics,
  WSNotification,
  Notification,
} from '@/types';

// =========================================================================
// CONSTANTS
// =========================================================================

const WS_BASE_URL =
  process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000/ws';

const RECONNECT_INTERVALS = [1000, 2000, 5000, 10000, 30000]; // ms
const HEARTBEAT_INTERVAL = 30_000; // 30 s
const MAX_RECONNECT_ATTEMPTS = 10;

// =========================================================================
// TYPES
// =========================================================================

export type WSStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

interface UseWebSocketReturn {
  isConnected: boolean;
  status: WSStatus;
  lastMessage: WSMessage | null;
  send: (type: WSMessageType, payload?: unknown) => void;
  reconnect: () => void;
  disconnect: () => void;
}

// =========================================================================
// HOOK
// =========================================================================

export function useWebSocket(): UseWebSocketReturn {
  const { accessToken, isAuthenticated } = useAuthStore();
  const { updateJobProgress, markJobCompleted, updateJobStatus } = useDiscoveryStore();
  const { setSystemStats, setLiveMetrics, setWsConnected, setHeartbeat } = useSystemStore();
  const { addNotification } = useUIStore();

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const shouldReconnectRef = useRef(true);
  const isMountedRef = useRef(true);

  const [status, setStatus] = useState<WSStatus>('disconnected');
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);

  // -----------------------------------------------------------------------
  // INTERNAL HELPERS
  // -----------------------------------------------------------------------

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const clearHeartbeat = useCallback(() => {
    if (heartbeatTimerRef.current) {
      clearInterval(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
    }
  }, []);

  const startHeartbeat = useCallback((ws: WebSocket) => {
    clearHeartbeat();
    heartbeatTimerRef.current = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'PING', payload: null, timestamp: new Date().toISOString() }));
        setHeartbeat(new Date().toISOString());
      }
    }, HEARTBEAT_INTERVAL);
  }, [clearHeartbeat, setHeartbeat]);

  // -----------------------------------------------------------------------
  // MESSAGE DISPATCH
  // -----------------------------------------------------------------------

  const dispatchMessage = useCallback(
    (message: WSMessage) => {
      setLastMessage(message);

      switch (message.type) {
        case 'DISCOVERY_PROGRESS': {
          const payload = message.payload as WSDiscoveryProgress;
          updateJobProgress(payload);
          break;
        }

        case 'DISCOVERY_COMPLETE': {
          const payload = message.payload as WSDiscoveryProgress;
          markJobCompleted(payload.jobId);
          addNotification({
            id: `notif-${Date.now()}`,
            title: 'Discovery Complete',
            message: `"${payload.jobName}" finished — ${payload.progress.discovered} businesses found.`,
            type: 'success',
            read: false,
            receivedAt: message.timestamp,
          } as Notification);
          break;
        }

        case 'DISCOVERY_FAILED': {
          const payload = message.payload as WSDiscoveryProgress;
          updateJobStatus(payload.jobId, 'failed');
          addNotification({
            id: `notif-${Date.now()}`,
            title: 'Discovery Failed',
            message: `"${payload.jobName}" failed. Please check the job details.`,
            type: 'error',
            read: false,
            receivedAt: message.timestamp,
          } as Notification);
          break;
        }

        case 'AUDIT_PROGRESS': {
          // Audit progress is handled locally via react-query invalidation or
          // dedicated audit store additions. Left as hook for future expansion.
          break;
        }

        case 'AUDIT_COMPLETE': {
          const payload = message.payload as WSAuditProgress;
          addNotification({
            id: `notif-${Date.now()}`,
            title: 'Audit Complete',
            message: `Audit for "${payload.businessName}" is ready.`,
            type: 'success',
            actionUrl: `/audits/${payload.auditId}`,
            read: false,
            receivedAt: message.timestamp,
          } as Notification);
          break;
        }

        case 'AUDIT_FAILED': {
          const payload = message.payload as WSAuditProgress;
          addNotification({
            id: `notif-${Date.now()}`,
            title: 'Audit Failed',
            message: `Audit for "${payload.businessName}" encountered an error.`,
            type: 'error',
            read: false,
            receivedAt: message.timestamp,
          } as Notification);
          break;
        }

        case 'EXPORT_COMPLETE': {
          addNotification({
            id: `notif-${Date.now()}`,
            title: 'Export Ready',
            message: 'Your export file is ready for download.',
            type: 'success',
            read: false,
            receivedAt: message.timestamp,
          } as Notification);
          break;
        }

        case 'SYSTEM_STATS': {
          setSystemStats(message.payload as WSSystemStats);
          break;
        }

        case 'LIVE_METRICS': {
          setLiveMetrics(message.payload as WSLiveMetrics);
          break;
        }

        case 'NOTIFICATION': {
          const payload = message.payload as WSNotification;
          addNotification({
            ...payload,
            receivedAt: message.timestamp,
          } as Notification);
          break;
        }

        case 'PONG': {
          // Heartbeat acknowledged
          break;
        }

        case 'ERROR': {
          console.error('[WS] Server error:', message.payload);
          break;
        }

        default:
          break;
      }
    },
    [
      updateJobProgress,
      markJobCompleted,
      updateJobStatus,
      setSystemStats,
      setLiveMetrics,
      addNotification,
    ]
  );

  // -----------------------------------------------------------------------
  // CONNECT
  // -----------------------------------------------------------------------

  const connect = useCallback(() => {
    if (!isAuthenticated || !accessToken) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    if (wsRef.current?.readyState === WebSocket.CONNECTING) return;

    const url = `${WS_BASE_URL}?token=${encodeURIComponent(accessToken)}`;

    try {
      setStatus('connecting');
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!isMountedRef.current) return;
        reconnectAttemptsRef.current = 0;
        setStatus('connected');
        setWsConnected(true);
        startHeartbeat(ws);
        clearReconnectTimer();
      };

      ws.onmessage = (event: MessageEvent<string>) => {
        if (!isMountedRef.current) return;
        try {
          const message = JSON.parse(event.data) as WSMessage;
          dispatchMessage(message);
        } catch (err) {
          console.warn('[WS] Failed to parse message:', err);
        }
      };

      ws.onerror = () => {
        if (!isMountedRef.current) return;
        setStatus('error');
      };

      ws.onclose = (event: CloseEvent) => {
        if (!isMountedRef.current) return;
        clearHeartbeat();
        setStatus('disconnected');
        setWsConnected(false);
        wsRef.current = null;

        // 4001 = unauthorized; do not reconnect
        if (event.code === 4001) return;

        if (
          shouldReconnectRef.current &&
          reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS
        ) {
          const delay =
            RECONNECT_INTERVALS[
              Math.min(reconnectAttemptsRef.current, RECONNECT_INTERVALS.length - 1)
            ];
          reconnectAttemptsRef.current += 1;
          reconnectTimerRef.current = setTimeout(() => {
            if (isMountedRef.current && shouldReconnectRef.current) {
              connect();
            }
          }, delay);
        }
      };
    } catch (err) {
      console.error('[WS] Failed to create WebSocket:', err);
      setStatus('error');
    }
  }, [
    isAuthenticated,
    accessToken,
    clearHeartbeat,
    clearReconnectTimer,
    dispatchMessage,
    setWsConnected,
    startHeartbeat,
  ]);

  // -----------------------------------------------------------------------
  // DISCONNECT
  // -----------------------------------------------------------------------

  const disconnect = useCallback(() => {
    shouldReconnectRef.current = false;
    clearReconnectTimer();
    clearHeartbeat();
    if (wsRef.current) {
      wsRef.current.close(1000, 'Client disconnect');
      wsRef.current = null;
    }
    setStatus('disconnected');
    setWsConnected(false);
  }, [clearHeartbeat, clearReconnectTimer, setWsConnected]);

  // -----------------------------------------------------------------------
  // RECONNECT (manual)
  // -----------------------------------------------------------------------

  const reconnect = useCallback(() => {
    disconnect();
    shouldReconnectRef.current = true;
    reconnectAttemptsRef.current = 0;
    connect();
  }, [connect, disconnect]);

  // -----------------------------------------------------------------------
  // SEND
  // -----------------------------------------------------------------------

  const send = useCallback((type: WSMessageType, payload: unknown = null) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({ type, payload, timestamp: new Date().toISOString() })
      );
    } else {
      console.warn('[WS] Cannot send — socket not open');
    }
  }, []);

  // -----------------------------------------------------------------------
  // LIFECYCLE
  // -----------------------------------------------------------------------

  useEffect(() => {
    isMountedRef.current = true;
    shouldReconnectRef.current = true;

    if (isAuthenticated && accessToken) {
      connect();
    }

    return () => {
      isMountedRef.current = false;
      shouldReconnectRef.current = false;
      clearReconnectTimer();
      clearHeartbeat();
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmounted');
        wsRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated, accessToken]);

  return {
    isConnected: status === 'connected',
    status,
    lastMessage,
    send,
    reconnect,
    disconnect,
  };
}

export default useWebSocket;
