import React from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts';

interface PortfolioChartProps {
  data: Record<string, number>;
}

const COLORS = ['#ffffff', '#a3a3a3', '#525252', '#262626', '#171717'];

const PortfolioChart: React.FC<PortfolioChartProps> = ({ data }) => {
  const chartData = Object.entries(data).map(([name, value]) => ({ name, value }));

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={80}
            paddingAngle={5}
            dataKey="value"
            stroke="none"
          >
            {chartData.map((_, index) => (
              <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip 
            contentStyle={{ backgroundColor: '#000000', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '0px', fontSize: '8px', fontFamily: 'monospace' }}
            itemStyle={{ color: '#ffffff' }}
          />
          <Legend iconType="rect" wrapperStyle={{ fontSize: '8px', paddingTop: '10px', fontFamily: 'monospace', textTransform: 'uppercase' }} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
};

export default PortfolioChart;
