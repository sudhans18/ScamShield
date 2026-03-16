import React, { useEffect, useState } from 'react';
import { ShieldCheck, Users, Search, AlertTriangle } from 'lucide-react';
import StatCard from '../components/StatCard';
import TrendChart from '../components/TrendChart';
import HeatMap from '../components/HeatMap';
import NetworkGraph from '../components/NetworkGraph';
import ReportTable from '../components/ReportTable';
import RiskDistribution from '../components/RiskDistribution';
import { fetchStats, fetchReports, fetchHeatmap, fetchTrends, fetchNetwork } from '../services/api';

const Dashboard = () => {
  const [data, setData] = useState({
    stats: null,
    reports: [],
    heatmap: [],
    trends: [],
    network: null
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadDashboardData = async () => {
      try {
        setLoading(true);
        const [statsData, reportsData, heatmapData, trendsData, networkData] = await Promise.all([
          fetchStats(),
          fetchReports(),
          fetchHeatmap(),
          fetchTrends(),
          fetchNetwork()
        ]);
        
        setData({
          stats: statsData,
          reports: reportsData,
          heatmap: heatmapData,
          trends: trendsData,
          network: networkData
        });
      } catch (error) {
        console.error("Error loading dashboard data", error);
      } finally {
        setLoading(false);
      }
    };

    loadDashboardData();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Dashboard Overview</h1>
          <p className="text-gray-400 mt-1">Real-time monitoring of scam reports and analytics</p>
        </div>
        <div className="flex items-center gap-2 text-sm text-gray-400 bg-card/50 px-4 py-2 rounded-full border border-white/5">
          <span className="w-2 h-2 rounded-full bg-secondary animate-pulse"></span>
          System Status: Operational
        </div>
      </div>

      {/* Stats Area */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard 
          title="Total Scam Reports" 
          value={data.stats?.totalReports} 
          icon={<AlertTriangle className="w-6 h-6" />} 
          type="danger"
          loading={loading}
        />
        <StatCard 
          title="Suspicious Phone Numbers" 
          value={data.stats?.suspiciousNumbers} 
          icon={<Search className="w-6 h-6" />} 
          type="warning"
          loading={loading}
        />
        <StatCard 
          title="Detected Networks" 
          value={data.stats?.detectedSyndicates} 
          icon={<Users className="w-6 h-6" />} 
          type="primary"
          loading={loading}
        />
        <StatCard 
          title="Verified Companies" 
          value={data.stats?.verifiedCompanies} 
          icon={<ShieldCheck className="w-6 h-6" />} 
          type="success"
          loading={loading}
        />
      </div>

      {/* Charts Area - Row 2 & 3 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 flex flex-col gap-6">
          <TrendChart data={data.trends} loading={loading} />
          <RiskDistribution />
        </div>
        <div className="lg:col-span-2">
          <NetworkGraph data={data.network} loading={loading} />
        </div>
      </div>

      {/* HeatMap - Row 4 */}
      <div className="w-full">
        <HeatMap data={data.heatmap} loading={loading} />
      </div>

      {/* Reports Table - Row 5 */}
      <div className="w-full">
        <ReportTable reports={data.reports} loading={loading} />
      </div>
    </div>
  );
};

export default Dashboard;
