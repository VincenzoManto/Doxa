import { formatNumber } from '../utils';
import type { MacroMetrics } from '../types';

export function MacroPanel({ macro }: { macro: MacroMetrics | null }) {
  if (!macro) {
    return (
      <section className="panel compact-panel macro-panel">
        <div className="panel-header">
          <div><p className="eyebrow">Macro</p><h3>Economic metrics</h3></div>
        </div>
        <div className="empty-state">No macro data yet.</div>
      </section>
    );
  }
  const panicPct = Math.min(100, Math.round(macro.system_panic * 100));
  const panicColor = panicPct >= 60 ? '#b42318' : panicPct >= 30 ? '#d97731' : '#2e8b57';
  return (
    <section className="panel compact-panel macro-panel">
      <div className="panel-header">
        <div><p className="eyebrow">Macro</p><h3>Economic metrics</h3></div>
        <span className="macro-tick">tick {macro.tick}</span>
      </div>

      <div className="macro-panic-row">
        <span>System panic</span>
        <div className="macro-bar-track">
          <div className="macro-bar-fill" style={{ width: `${panicPct}%`, background: panicColor }} />
        </div>
        <strong style={{ color: panicColor }}>{macro.system_panic.toFixed(3)}</strong>
      </div>

      {Object.keys(macro.resources).length > 0 && (
        <div className="macro-section-label">Resources</div>
      )}
      <div className="macro-stat-grid">
        {Object.entries(macro.resources).map(([res, stat]) => (
          <div key={res} className="macro-stat-card">
            <span className="macro-stat-name">{res}</span>
            <div className="macro-stat-row"><span>Total</span><strong>{formatNumber(stat.total, 2)}</strong></div>
            <div className="macro-stat-row"><span>Gini</span><strong className={stat.gini > 0.5 ? 'macro-warn' : ''}>{stat.gini.toFixed(3)}</strong></div>
            <div className="macro-stat-row"><span>HHI</span><strong className={stat.hhi > 0.5 ? 'macro-warn' : ''}>{stat.hhi.toFixed(3)}</strong></div>
          </div>
        ))}
      </div>

      {Object.keys(macro.market_stats).length > 0 && (
        <div className="macro-section-label">Markets</div>
      )}
      <div className="macro-stat-grid">
        {Object.entries(macro.market_stats).map(([res, mstat]) => (
          <div key={res} className="macro-stat-card">
            <span className="macro-stat-name">{res}</span>
            <div className="macro-stat-row"><span>Last</span><strong>{formatNumber(mstat.last_price, 4)}</strong></div>
            <div className="macro-stat-row"><span>Volatility</span><strong className={mstat.volatility > 0.5 ? 'macro-warn' : ''}>{mstat.volatility.toFixed(4)}</strong></div>
            <div className="macro-stat-row"><span>Range</span><strong>{formatNumber(mstat.min_recent, 2)}–{formatNumber(mstat.max_recent, 2)}</strong></div>
          </div>
        ))}
      </div>
    </section>
  );
}