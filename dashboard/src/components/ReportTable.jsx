import React from 'react';
import { AlertCircle, AlertTriangle, CheckCircle2, MapPin, Clock } from 'lucide-react';

const ReportTable = ({ reports, loading }) => {
  if (loading) {
    return (
      <div className="glassmorphism rounded-2xl p-6 h-96 flex flex-col gap-4">
        <h3 className="text-xl font-bold">Recent Scam Reports</h3>
        <div className="space-y-4 flex-1">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-12 w-full bg-white/5 rounded animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  const getRiskColor = (score) => {
    switch (score) {
      case 'High Risk': return 'text-danger bg-danger/10 border-danger/20';
      case 'Suspicious': return 'text-warning bg-warning/10 border-warning/20';
      case 'Safe': return 'text-secondary bg-secondary/10 border-secondary/20';
      default: return 'text-gray-400 bg-gray-500/10 border-gray-500/20';
    }
  };

  const getRiskIcon = (score) => {
    switch (score) {
      case 'High Risk': return <AlertCircle className="w-4 h-4" />;
      case 'Suspicious': return <AlertTriangle className="w-4 h-4" />;
      case 'Safe': return <CheckCircle2 className="w-4 h-4" />;
      default: return null;
    }
  };

  return (
    <div className="glassmorphism rounded-2xl overflow-hidden shadow-xl border border-white/10">
      <div className="p-6 border-b border-white/5 bg-card/50">
        <h3 className="text-xl font-bold tracking-tight">Recent Scam Reports</h3>
      </div>
      <div className="w-full overflow-x-auto">
        <table className="w-full text-left text-sm whitespace-nowrap">
          <thead className="bg-black/20 text-gray-400 text-xs uppercase tracking-wider">
            <tr>
              <th className="px-6 py-4 font-medium">Phone Number</th>
              <th className="px-6 py-4 font-medium">Message Preview</th>
              <th className="px-6 py-4 font-medium">Risk Score</th>
              <th className="px-6 py-4 font-medium">Location</th>
              <th className="px-6 py-4 font-medium">Timestamp</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5 text-gray-300">
            {reports.map((report) => (
              <tr key={report.id} className="hover:bg-white/5 transition-colors group">
                <td className="px-6 py-4 font-medium text-white group-hover:text-primary transition-colors">
                  {report.phone}
                </td>
                <td className="px-6 py-4">
                  <div className="max-w-xs truncate text-gray-400 group-hover:text-gray-300">
                    {report.message}
                  </div>
                </td>
                <td className="px-6 py-4">
                  <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border ${getRiskColor(report.riskScore)}`}>
                    {getRiskIcon(report.riskScore)}
                    {report.riskScore}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <div className="flex items-center gap-1.5 text-gray-400">
                    <MapPin className="w-4 h-4" />
                    {report.location}
                  </div>
                </td>
                <td className="px-6 py-4 text-gray-500">
                  <div className="flex items-center gap-1.5">
                    <Clock className="w-4 h-4" />
                    {report.timestamp}
                  </div>
                </td>
              </tr>
            ))}
            {reports.length === 0 && (
              <tr>
                <td colSpan="5" className="px-6 py-12 text-center text-gray-500">
                  No recent reports found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default ReportTable;
