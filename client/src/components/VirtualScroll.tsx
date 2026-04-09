// ---------------------------------------------------------------------------
// Generic VirtualScroll — renders only the rows in the visible viewport.
// itemHeight must be fixed and include any gap/margin between items.
// ---------------------------------------------------------------------------
export function VirtualScroll<T>({ items, itemHeight, visibleHeight, renderItem, className, autoScrollBottom = false }: { items: T[]; itemHeight: number; visibleHeight: number; renderItem: (item: T, index: number) => React.ReactNode; className?: string; autoScrollBottom?: boolean }) {
 

  return (
    <div className={className} style={{ height: visibleHeight, overflowY: 'auto', position: 'relative' }}>
      <div style={{ display: 'flex', flexDirection: 'column', position: 'relative', gap: '1rem' }}>
        {items.map((item, i) => (
          <div key={i} >
            {renderItem(item,i)}
          </div>
        ))}
      </div>
    </div>
  );
}