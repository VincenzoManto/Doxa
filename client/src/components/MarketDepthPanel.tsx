import { formatNumber } from '../utils';
import type { MarketOrderBook, MarketSummary } from '../types';
export function MarketDepthPanel({ markets, selectedMarket, onSelectMarket, orderBook }: { markets: Record<string, MarketSummary>; selectedMarket: string; onSelectMarket: (resource: string) => void; orderBook: MarketOrderBook | null }) {
  const marketList = Object.values(markets).sort((left, right) => left.resource.localeCompare(right.resource));

  return (
    <section className="panel compact-panel market-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Market</p>
          <h3>Order book</h3>
        </div>
      </div>
      {marketList.length === 0 ? (
        <div className="empty-state">No configured markets in this scenario.</div>
      ) : (
        <>
          <div className="market-selector-list">
            {marketList.map((market) => (
              <button key={market.resource} type="button" className={`market-chip${selectedMarket === market.resource ? ' market-chip-active' : ''}`} onClick={() => onSelectMarket(market.resource)}>
                <span>{market.resource}/{market.currency}</span>
                <strong>{formatNumber(market.current_price, 4)}</strong>
              </button>
            ))}
          </div>
          {orderBook && (
            <>
              <div className="market-price-strip">
                <div className="market-price-card">
                  <span>Last</span>
                  <strong>{formatNumber(orderBook.last_price, 4)}</strong>
                </div>
                <div className="market-price-card">
                  <span>Mid</span>
                  <strong>{formatNumber(orderBook.mid_price, 4)}</strong>
                </div>
                <div className="market-price-card">
                  <span>Spread</span>
                  <strong>{formatNumber((orderBook.asks[0]?.price ?? orderBook.last_price) - (orderBook.bids[0]?.price ?? orderBook.last_price), 4)}</strong>
                </div>
              </div>
              <div className="orderbook-shell">
                <div className="orderbook-side">
                  <div className="orderbook-head orderbook-head-bid">
                    <span>Bids</span>
                    <span>Qty @ Price</span>
                  </div>
                  {(orderBook.bids.length ? orderBook.bids : [{ price: 0, qty: 0 }]).map((level, index) => (
                    <div key={`bid-${index}-${level.price}`} className={`orderbook-row${orderBook.bids.length ? ' orderbook-row-bid' : ' orderbook-row-empty'}`}>
                      {orderBook.bids.length ? (
                        <>
                          <span>{formatNumber(level.qty, 4)}</span>
                          <strong>{formatNumber(level.price, 4)}</strong>
                        </>
                      ) : (
                        <span className="orderbook-empty">No bids</span>
                      )}
                    </div>
                  ))}
                </div>
                <div className="orderbook-side">
                  <div className="orderbook-head orderbook-head-ask">
                    <span>Asks</span>
                    <span>Qty @ Price</span>
                  </div>
                  {(orderBook.asks.length ? orderBook.asks : [{ price: 0, qty: 0 }]).map((level, index) => (
                    <div key={`ask-${index}-${level.price}`} className={`orderbook-row${orderBook.asks.length ? ' orderbook-row-ask' : ' orderbook-row-empty'}`}>
                      {orderBook.asks.length ? (
                        <>
                          <span>{formatNumber(level.qty, 4)}</span>
                          <strong>{formatNumber(level.price, 4)}</strong>
                        </>
                      ) : (
                        <span className="orderbook-empty">No asks</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}