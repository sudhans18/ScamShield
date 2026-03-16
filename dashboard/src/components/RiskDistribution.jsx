import React from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts';

const data = [
  { name: 'High Risk', value: 45 },
  { name: 'Suspicious', value: 30 },
  { name: 'Safe', value: 25 },
];

const COLORS = {
  'High Risk': '#EF4444',
  'Suspicious': '#F59E0B',
  'Safe': '#10B981',
};

const RiskDistribution = () => {
  return (
    <div className="glassmorphism rounded-2xl p-4 h-[280px] flex flex-col shadow-xl border border-white/10 relative overflow-hidden">
      <div className="flex justify-between items-center mb-2 px-2 z-10">
        <h3 className="text-xl font-bold tracking-tight">Scam Risk Distribution</h3>
      </div>
      <div className="flex-1 w-full bg-card/30 rounded-xl relative border border-white/5 pb-4">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              innerRadius={60}
              outerRadius={80}
              paddingAngle={5}
              dataKey="value"
              stroke="none"
            >
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[entry.name]} />
              ))}
            </Pie>
            <Tooltip 
              contentStyle={{ backgroundColor: 'rgba(17, 24, 39, 0.8)', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '8px', color: '#f3f4f6' }}
              itemStyle={{ color: '#f3f4f6' }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default RiskDistribution;
