import React, { useMemo } from 'react';
import ForceGraph2D from 'react-force-graph-2d';

interface NetworkGraphProps {
  actors: any;
  messages: any[];
}

const NetworkGraph: React.FC<NetworkGraphProps> = ({ actors, messages }) => {
  const graphData = useMemo(() => {
    const nodes = Object.values(actors).map((a: any) => ({
      id: a.id,
      name: a.name,
      val: 5
    }));

    const links: any[] = [];
    const linkMap = new Map();

    messages.forEach(msg => {
      if (msg.type === 'private' && msg.target) {
        const key = `${msg.sender}-${msg.target}`;
        linkMap.set(key, (linkMap.get(key) || 0) + 1);
      }
    });

    linkMap.forEach((val, key) => {
      const [source, target] = key.split('-');
      links.push({ source, target, value: val });
    });

    return { nodes, links };
  }, [actors, messages]);

  return (
    <div className="h-full w-full">
      <ForceGraph2D
        graphData={graphData}
        nodeLabel="name"
        nodeColor={() => '#ffffff'}
        nodeRelSize={4}
        linkColor={() => 'rgba(255, 255, 255, 0.1)'}
        linkDirectionalArrowLength={3}
        linkDirectionalArrowRelPos={1}
        linkCurvature={0.2}
        backgroundColor="rgba(0,0,0,0)"
        width={600}
        height={400}
      />
    </div>
  );
};

export default NetworkGraph;
