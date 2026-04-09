import React, { useEffect, useRef } from 'react';
import { formatNumber, formatTimestamp, findTimelineEventIndex, pointLabel } from '../utils';
import type { LiveEvent } from '../types';
export function EventBody({ event }: { event: LiveEvent }) {
  if (event.type === 'trade') {
    const g = event.give;
    const t = event.take;
    const ok = String(event.result ?? '').startsWith('SUCCESS');
    return (
      <span className="log-body">
        <strong className="log-actor">{event.agent}</strong>
        <span className="log-arrow"> → </span>
        <strong className="log-target">{event.target}</strong>
        {g && t && (
          <span className="log-detail">
            {': '}
            <span className="log-give">
              {g.qty}×{g.resource}
            </span>
            <span className="log-swap"> ⇄ </span>
            <span className="log-take">
              {t.qty}×{t.resource}
            </span>
          </span>
        )}
        <span className={ok ? 'log-result-ok' : 'log-result-fail'}> — {String(event.result ?? '')}</span>
      </span>
    );
  }
  if (event.type === 'communication') {
    return (
      <span className="log-body">
        <strong className="log-actor">{event.agent}</strong>
        <span className="log-arrow"> → </span>
        <strong className="log-target">{event.target ?? 'ALL'}</strong>
        <span className="log-message">: “{event.text}”</span>
      </span>
    );
  }
  if (event.type === 'action') {
    const hasTarget = event.target && event.target !== 'undefined' && event.target !== 'null';
    const ok = String(event.result ?? '').startsWith('SUCCESS');
    const actionName = event.action ?? '';
    const isTradeAction = /trade/i.test(actionName);
    const trdMatch = isTradeAction ? String(event.result ?? '').match(/TRD_\d+/) : null;
    return (
      <span className="log-body">
        <strong className="log-actor">{event.agent}</strong>
        {hasTarget && (
          <>
            <span className="log-arrow"> → </span>
            <strong className="log-target">{event.target}</strong>
          </>
        )}
        <span className="log-action"> [{event.action}]</span>
        {trdMatch && <span className="log-trade-id"> {trdMatch[0]}</span>}
        {event.result !== undefined && <span className={ok ? 'log-result-ok' : 'log-result-fail'}> — {String(event.result)}</span>}
      </span>
    );
  }
  if (event.type === 'think') {
    return (
      <span className="log-body">
        <strong className="log-actor">{event.agent}</strong>
        <span className="log-think"> thinks </span>
        <em className="log-message">“{event.thought}”</em>
      </span>
    );
  }
  if (event.type === 'kill') {
    return (
      <span className="log-body">
        <strong className="log-actor">{event.agent}</strong>
        <span className="log-kill"> eliminated</span>
        {event.reason && <span> — {event.reason}</span>}
      </span>
    );
  }
  if (event.type === 'victory') {
    return <span className="log-body log-victory">{event.text}</span>;
  }
  if (event.type === 'market_fill') {
    return (
      <span className="log-body">
        <strong className="log-actor">{event.buyer}</strong>
        <span className="log-arrow"> ← </span>
        <strong className="log-target">{event.seller}</strong>
        <span className="log-detail">
          {': '}
          <span className="log-take">{formatNumber(event.qty, 4)}×{event.resource}</span>
          <span className="log-swap"> @ </span>
          <span className="log-give">{formatNumber(event.price, 4)}</span>
        </span>
      </span>
    );
  }
  if (event.type === 'world_event') {
    return (
      <span className="log-body">
        <strong className="log-actor">{event.text ?? 'world_event'}</strong>
        {Array.isArray(event.effects) && event.effects.length > 0 && <span className="log-detail"> — {event.effects.join(' · ')}</span>}
      </span>
    );
  }
  if (event.type === 'epoch') {
    return <span className="log-body log-epoch">Epoch {event.epoch} started</span>;
  }
  if (event.type === 'step') {
    return <span className="log-body log-muted">Global step {event.step}</span>;
  }
  return <span className="log-body log-muted">{event.text ?? JSON.stringify(event)}</span>;
}

export function EventLine({ event }: { event: LiveEvent }) {
  return (
    <div className="log-row">
      <span className="log-time">{formatTimestamp(event.timestamp)}</span>
      <span className={`log-type log-type-${event.type}`}>{event.type}</span>
      <EventBody event={event} />
    </div>
  );
}