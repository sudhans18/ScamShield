import React from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';

const COLORS = {
  'High Risk': '#EF4444',
  Suspicious: '#F59E0B',
  Safe: '#10B981',
};

const buildDistribution = (reports = []) => {
  const counts = reports.reduce(
    (accumulator, report) => {
      const key = report.riskScore;
      if (Object.prototype.hasOwnProperty.call(accumulator, key)) {
        accumulator[key] += 1;
      }
      return accumulator;
    },
    { 'High Risk': 0, Suspicious: 0, Safe: 0 }
  );

  return Object.entries(counts).map(([name, value]) => ({ name, value }));
};

const RiskDistribution = ({ reports = [], loading }) => {
  if (loading) {
    return (
      <div className="glassmorphism rounded-2xl p-6 h-[340px] flex flex-col justify-center items-center shadow-xl border border-white/10">
        <div className="w-12 h-12 border-4 border-primary/20 border-t-primary rounded-full animate-spin"></div>
        <p className="text-gray-500 mt-4 text-sm font-medium">Loading distribution...</p>
      </div>
    );
  }

  const data = buildDistribution(reports);
  const hasData = data.some((entry) => entry.value > 0);

  return (
    <div className="glassmorphism rounded-2xl p-4 h-[340px] flex flex-col shadow-xl border border-white/10 relative overflow-hidden">
      <div className="flex justify-between items-center mb-2 px-2 z-10">
        <h3 className="text-xl font-bold tracking-tight">Scam Risk Distribution</h3>
      </div>
      <div className="flex-1 w-full bg-card/30 rounded-xl relative border border-white/5 pb-4">
        {hasData ? (
          <ResponsiveContainer width="100%" height="100%">
            <PieChart margin={{ top: 0, right: 0, left: 0, bottom: 20 }}>
              <Pie
                data={data}
                cx="50%"
                cy="42%"
                innerRadius={50}
                outerRadius={70}
                paddingAngle={4}
                dataKey="value"
                nameKey="name"
                stroke="none"
              >
                {data.map((entry) => (
                  <Cell key={entry.name} fill={COLORS[entry.name]} />
                ))}
              </Pie>
              <Tooltip
                formatter={(value) => [`${value} reports`, 'Count']}
                contentStyle={{
                  backgroundColor: 'rgba(17, 24, 39, 0.92)',
                  borderColor: 'rgba(255,255,255,0.1)',
                  borderRadius: '8px',
                  color: '#f3f4f6',
                }}
                itemStyle={{ color: '#f3f4f6' }}
              />
              <Legend verticalAlign="bottom" height={36} iconType="circle" wrapperStyle={{ bottom: 0 }} />
            </PieChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-full flex items-center justify-center text-sm text-gray-500 text-center px-6">
            No reports available yet to calculate the risk distribution.
          </div>
        )}
      </div>
    </div>
  );
};

export default RiskDistribution;
