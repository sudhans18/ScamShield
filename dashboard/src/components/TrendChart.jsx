import React from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from 'recharts';

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="glassmorphism p-4 rounded-lg border border-white/10 shadow-2xl">
        <p className="text-gray-400 text-sm mb-1">{`Date: ${label}`}</p>
        <p className="text-primary font-bold text-lg">
          {`${payload[0].value} Reports`}
        </p>
      </div>
    );
  }
  return null;
};

const TrendChart = ({ data, loading }) => {
  if (loading) {
    return (
      <div className="glassmorphism rounded-2xl p-6 h-96 flex flex-col justify-center items-center">
        <div className="animate-pulse flex items-center gap-2">
          <div className="w-4 h-12 bg-primary/20 rounded-t" />
          <div className="w-4 h-24 bg-primary/20 rounded-t" />
          <div className="w-4 h-16 bg-primary/40 rounded-t" />
          <div className="w-4 h-32 bg-primary/60 rounded-t" />
          <div className="w-4 h-20 bg-primary/80 rounded-t" />
          <div className="w-4 h-40 bg-primary rounded-t" />
        </div>
        <p className="text-gray-500 mt-4 text-sm font-medium">Loading Trends...</p>
      </div>
    );
  }

  return (
    <div className="glassmorphism rounded-2xl p-6 h-96 flex flex-col shadow-xl border border-white/10">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h3 className="text-xl font-bold tracking-tight">Scam Reports Trend</h3>
          <p className="text-sm text-gray-400">Daily volume of reported incidents</p>
        </div>
        <div className="flex items-center gap-2 text-sm text-secondary font-medium">
          <span className="w-2 h-2 rounded-full bg-secondary animate-pulse" />
          Live updates
        </div>
      </div>
      
      <div className="flex-1 w-full min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={data}
            margin={{
              top: 10,
              right: 10,
              left: -20,
              bottom: 0,
            }}
          >
            <defs>
              <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.4}/>
                <stop offset="95%" stopColor="#3B82F6" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
            <XAxis 
              dataKey="date" 
              stroke="#6B7280" 
              fontSize={12} 
              tickLine={false}
              axisLine={false}
              dy={10}
            />
            <YAxis 
              stroke="#6B7280" 
              fontSize={12}
              tickLine={false}
              axisLine={false}
              dx={-10}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ stroke: 'rgba(255,255,255,0.1)', strokeWidth: 1, strokeDasharray: '3 3' }} />
            <Area 
              type="monotone" 
              dataKey="count" 
              stroke="#3B82F6" 
              strokeWidth={3}
              fillOpacity={1} 
              fill="url(#colorCount)" 
              activeDot={{ r: 6, strokeWidth: 0, fill: '#3B82F6', style: { filter: 'drop-shadow(0px 0px 8px rgba(59, 130, 246, 0.8))' } }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default TrendChart;
