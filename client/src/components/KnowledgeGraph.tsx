import React, { useEffect, useRef } from 'react';
import * as echarts from 'echarts';
import type { AgentMemoryGraph } from '../types';

export function KnowledgeGraph({ graph, onSelectDoc, selectedDocId }: { graph: AgentMemoryGraph | null; onSelectDoc: (docId: string) => void; selectedDocId: string | null }) {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const chartInstanceRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!chartRef.current || !graph || graph.graph.nodes.length === 0) {
      return;
    }
    if (!chartInstanceRef.current) {
      chartInstanceRef.current = echarts.init(chartRef.current);
    }
    const chart = chartInstanceRef.current;
    chart.setOption(
      {
        animationDuration: 300,
        backgroundColor: 'transparent',
        tooltip: {
          backgroundColor: '#ffffff',
          borderColor: '#dde5ed',
          textStyle: { color: '#1d2d3a' },
          formatter: (params: { data?: Record<string, unknown> }) => {
            const data = params.data ?? {};
            const preview = typeof data.preview === 'string' ? data.preview : '';
            const tokens = Array.isArray(data.tokens) ? data.tokens.join(', ') : '';
            return `${String(data.name ?? '')}${preview ? `<br/>${preview}` : ''}${tokens ? `<br/><span style="color:#6b8194">${tokens}</span>` : ''}`;
          },
        },
        series: [
          {
            type: 'graph',
            layout: 'force',
            roam: true,
            draggable: true,
            force: { repulsion: 180, edgeLength: [70, 130] },
            label: { show: true, color: '#1d2d3a', fontSize: 11 },
            lineStyle: { color: '#cbd7e3', opacity: 0.8, width: 1.2 },
            categories: [{ name: 'agent' }, { name: 'memory' }],
            data: graph.graph.nodes.map((node) => {
              const category = node.category === 'agent' ? 0 : 1;
              return {
                ...node,
                category,
                itemStyle: {
                  color: category === 0 ? '#2060a0' : '#d97731',
                  borderColor: selectedDocId === node.id ? '#1d2d3a' : '#ffffff',
                  borderWidth: selectedDocId === node.id ? 3 : 1,
                },
              };
            }),
            links: graph.graph.edges,
          },
        ],
      },
      { notMerge: false, lazyUpdate: true, replaceMerge: ['series'] },
    );
    chart.off('click');
    chart.on('click', (params) => {
      const data = (params.data ?? null) as Record<string, unknown> | null;
      const nodeId = typeof data?.id === 'string' ? data.id : null;
      const category = data?.category;
      if (nodeId && category !== 0) {
        onSelectDoc(nodeId);
      }
    });
    const resizeObserver = new ResizeObserver(() => chart.resize());
    resizeObserver.observe(chartRef.current);
    return () => {
      resizeObserver.disconnect();
    };
  }, [graph, onSelectDoc, selectedDocId]);

  useEffect(
    () => () => {
      chartInstanceRef.current?.dispose();
      chartInstanceRef.current = null;
    },
    [],
  );

  const isEmpty = !graph || graph.stats.documents === 0;

  return (
    <>
      {isEmpty ? <div className="empty-state">No ChromaDB knowledge stored for this agent.</div> : null}
      <div ref={chartRef} className="kb-graph-canvas" style={{ display: isEmpty ? 'none' : undefined }} />
    </>
  );
}