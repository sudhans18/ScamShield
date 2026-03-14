import React, { useEffect } from 'react';
import { MapContainer, TileLayer, CircleMarker, Tooltip } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';

// Approximate coordinates for major Indian states
const stateCoordinates = {
  "Maharashtra": [19.7515, 75.7139],
  "Delhi": [28.7041, 77.1025],
  "Uttar Pradesh": [26.8467, 80.9462],
  "Karnataka": [15.3173, 75.7139],
  "West Bengal": [22.9868, 87.8550],
  "Tamil Nadu": [11.1271, 78.6569],
  "Bihar": [25.0961, 85.3131],
  "Rajasthan": [27.0238, 74.2179],
  "Gujarat": [22.2587, 71.1924],
  "Telangana": [18.1124, 79.0193],
};

const HeatMap = ({ data, loading }) => {
  if (loading) {
    return (
      <div className="glassmorphism rounded-2xl p-6 h-96 flex flex-col justify-center items-center">
        <div className="w-16 h-16 border-4 border-primary/20 border-t-primary rounded-full animate-spin"></div>
        <p className="text-gray-500 mt-4 text-sm font-medium">Loading Map Data...</p>
      </div>
    );
  }

  // Find max count for relative sizing
  const maxCount = Math.max(...(data?.map(d => d.count) || [1]));

  return (
    <div className="glassmorphism rounded-2xl p-4 h-[450px] flex flex-col shadow-xl border border-white/10 relative z-0">
      <div className="flex justify-between items-center mb-4 px-2 relative z-10 pointer-events-none">
        <div>
          <h3 className="text-xl font-bold tracking-tight">India Scam Heatmap</h3>
          <p className="text-sm text-gray-400">Geographic distribution of reported scams</p>
        </div>
      </div>
      
      <div className="flex-1 w-full rounded-xl overflow-hidden relative z-0">
        <MapContainer 
          center={[22.5937, 78.9629]} // Center of India
          zoom={4.5} 
          scrollWheelZoom={false}
          style={{ height: '100%', width: '100%', background: '#0B0F19' }}
          attributionControl={false}
        >
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          />
          
          {data?.map((item, index) => {
            const coords = stateCoordinates[item.state];
            if (!coords) return null;
            
            // Calculate relative size based on count
            const radius = Math.max(8, (item.count / maxCount) * 25);
            
            // Determine risk color intensity
            const intensity = item.count / maxCount;
            let color = '#3B82F6'; // default primary
            if (intensity > 0.7) color = '#EF4444'; // danger
            else if (intensity > 0.4) color = '#F59E0B'; // warning

            return (
              <CircleMarker
                key={index}
                center={coords}
                pathOptions={{
                  color: color,
                  fillColor: color,
                  fillOpacity: 0.6,
                  weight: 1
                }}
                radius={radius}
              >
                <Tooltip direction="top" offset={[0, -10]} opacity={1} className="bg-card text-white border-0 shadow-xl">
                  <div className="p-1">
                    <p className="font-bold text-sm mb-1">{item.state}</p>
                    <p className="text-gray-300 text-xs flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: color }}></span>
                      {item.count} Reports
                    </p>
                  </div>
                </Tooltip>
              </CircleMarker>
            );
          })}
        </MapContainer>
      </div>
    </div>
  );
};

export default HeatMap;
