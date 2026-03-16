import React, { useMemo } from 'react';
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';

const locationCoordinates = {
  maharashtra: { lat: 19.7515, lng: 75.7139, label: 'Maharashtra' },
  mumbai: { lat: 19.0760, lng: 72.8777, label: 'Mumbai' },
  pune: { lat: 18.5204, lng: 73.8567, label: 'Pune' },
  delhi: { lat: 28.7041, lng: 77.1025, label: 'Delhi' },
  newdelhi: { lat: 28.6139, lng: 77.2090, label: 'Delhi' },
  uttarpradesh: { lat: 26.8467, lng: 80.9462, label: 'Uttar Pradesh' },
  up: { lat: 26.8467, lng: 80.9462, label: 'Uttar Pradesh' },
  lucknow: { lat: 26.8467, lng: 80.9462, label: 'Lucknow' },
  noida: { lat: 28.5355, lng: 77.3910, label: 'Noida' },
  ghaziabad: { lat: 28.6692, lng: 77.4538, label: 'Ghaziabad' },
  karnataka: { lat: 15.3173, lng: 75.7139, label: 'Karnataka' },
  bengaluru: { lat: 12.9716, lng: 77.5946, label: 'Bengaluru' },
  bangalore: { lat: 12.9716, lng: 77.5946, label: 'Bengaluru' },
  westbengal: { lat: 22.9868, lng: 87.8550, label: 'West Bengal' },
  kolkata: { lat: 22.5726, lng: 88.3639, label: 'Kolkata' },
  tamilnadu: { lat: 11.1271, lng: 78.6569, label: 'Tamil Nadu' },
  chennai: { lat: 13.0827, lng: 80.2707, label: 'Chennai' },
  bihar: { lat: 25.0961, lng: 85.3131, label: 'Bihar' },
  patna: { lat: 25.5941, lng: 85.1376, label: 'Patna' },
  rajasthan: { lat: 27.0238, lng: 74.2179, label: 'Rajasthan' },
  jaipur: { lat: 26.9124, lng: 75.7873, label: 'Jaipur' },
  gujarat: { lat: 22.2587, lng: 71.1924, label: 'Gujarat' },
  ahmedabad: { lat: 23.0225, lng: 72.5714, label: 'Ahmedabad' },
  telangana: { lat: 18.1124, lng: 79.0193, label: 'Telangana' },
  hyderabad: { lat: 17.3850, lng: 78.4867, label: 'Hyderabad' },
  kerala: { lat: 10.8505, lng: 76.2711, label: 'Kerala' },
  goa: { lat: 15.2993, lng: 74.1240, label: 'Goa' },
  madhyapradesh: { lat: 22.9734, lng: 78.6569, label: 'Madhya Pradesh' },
  bhopal: { lat: 23.2599, lng: 77.4126, label: 'Bhopal' },
  indore: { lat: 22.7196, lng: 75.8577, label: 'Indore' },
  andhrapradesh: { lat: 15.9129, lng: 79.7400, label: 'Andhra Pradesh' },
  vishakhapatnam: { lat: 17.6868, lng: 83.2185, label: 'Visakhapatnam' },
  assam: { lat: 26.2006, lng: 92.9376, label: 'Assam' },
  guwahati: { lat: 26.1445, lng: 91.7362, label: 'Guwahati' },
  punjab: { lat: 31.1471, lng: 75.3412, label: 'Punjab' },
  chandigarh: { lat: 30.7333, lng: 76.7794, label: 'Chandigarh' },
  ludhiana: { lat: 30.9010, lng: 75.8573, label: 'Ludhiana' },
  haryana: { lat: 29.0588, lng: 76.0856, label: 'Haryana' },
  gurugram: { lat: 28.4595, lng: 77.0266, label: 'Gurugram' },
  gurgaon: { lat: 28.4595, lng: 77.0266, label: 'Gurugram' },
  odisha: { lat: 20.9517, lng: 85.0985, label: 'Odisha' },
  bhubaneswar: { lat: 20.2961, lng: 85.8245, label: 'Bhubaneswar' },
  chhattisgarh: { lat: 21.2787, lng: 81.8661, label: 'Chhattisgarh' },
  raipur: { lat: 21.2514, lng: 81.6296, label: 'Raipur' },
  uttarakhand: { lat: 30.0668, lng: 79.0193, label: 'Uttarakhand' },
  dehradun: { lat: 30.3165, lng: 78.0322, label: 'Dehradun' },
  jharkhand: { lat: 23.6102, lng: 85.2799, label: 'Jharkhand' },
  ranchi: { lat: 23.3441, lng: 85.3096, label: 'Ranchi' },
  himachalpradesh: { lat: 31.1048, lng: 77.1665, label: 'Himachal Pradesh' },
  shimla: { lat: 31.1048, lng: 77.1734, label: 'Shimla' },
};

const normalizeLocation = (value = '') =>
  value.toLowerCase().replace(/[^a-z]/g, '');

const aggregateHeatPoints = (rows = []) => {
  const grouped = new Map();

  rows.forEach((row) => {
    const locationName = row.state || row.location || '';
    const normalized = normalizeLocation(locationName);
    const coords = locationCoordinates[normalized];

    if (!coords) {
      return;
    }

    const key = coords.label;
    const existing = grouped.get(key) || { ...coords, count: 0 };
    existing.count += Number(row.count || 0);
    grouped.set(key, existing);
  });

  return Array.from(grouped.values()).sort((left, right) => right.count - left.count);
};

const getBubbleColor = (intensity) => {
  if (intensity > 0.7) return '#ef4444';
  if (intensity > 0.4) return '#f59e0b';
  return '#3b82f6';
};

const HeatMap = ({ data, loading }) => {
  const points = useMemo(() => aggregateHeatPoints(data || []), [data]);

  if (loading) {
    return (
      <div className="glassmorphism rounded-2xl p-6 h-[500px] flex flex-col justify-center items-center">
        <div className="w-16 h-16 border-4 border-primary/20 border-t-primary rounded-full animate-spin"></div>
        <p className="text-gray-500 mt-4 text-sm font-medium">Loading map data...</p>
      </div>
    );
  }

  const maxCount = Math.max(...points.map((point) => point.count), 1);

  return (
    <div className="glassmorphism rounded-2xl p-4 h-[550px] flex flex-col shadow-xl border border-white/10 relative overflow-hidden">
      <div className="flex justify-between items-center mb-4 px-2">
        <div>
          <h3 className="text-xl font-bold tracking-tight">India Scam Heatmap</h3>
          <p className="text-sm text-gray-400">Geographic distribution of reported scams</p>
        </div>
      </div>

      <div className="flex-1 rounded-xl border border-white/5 bg-slate-900 overflow-hidden">
        <div className="grid h-full grid-cols-1 lg:grid-cols-[2fr_1fr]">
          <div className="relative min-h-[300px] h-full z-10 outline-none">
            <MapContainer 
              center={[22.5937, 78.9629]} 
              zoom={4} 
              scrollWheelZoom={false}
              className="h-full w-full outline-none"
              style={{ background: '#0f172a' }}
            >
              <TileLayer
                attribution='&copy; <a href="https://carto.com/attributions">CARTO</a>'
                url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
              />
              {points.map((point) => {
                const intensity = point.count / maxCount;
                const radius = 8 + intensity * 16;
                const color = getBubbleColor(intensity);

                return (
                  <CircleMarker
                    key={point.label}
                    center={[point.lat, point.lng]}
                    radius={radius}
                    pathOptions={{
                      fillColor: color,
                      fillOpacity: 0.6,
                      color: color,
                      weight: 1,
                      opacity: 0.8
                    }}
                  >
                    <Popup className="bg-card text-white border-white/10 shadow-2xl rounded-lg">
                      <div className="font-semibold text-base mb-1">{point.label}</div>
                      <div className="text-sm text-gray-300">Total Reports: <span className="text-white font-bold ml-1">{point.count}</span></div>
                    </Popup>
                  </CircleMarker>
                );
              })}
            </MapContainer>
          </div>

          <div className="border-t lg:border-t-0 lg:border-l border-white/5 bg-black/20 p-4 overflow-y-auto">
            <h4 className="text-sm font-semibold uppercase tracking-[0.18em] text-gray-400 mb-4 sticky top-0 bg-[#0f172a]/90 backdrop-blur pb-2">Top locations</h4>
            <div className="space-y-4">
              {points.length > 0 ? (
                points.slice(0, 8).map((point) => {
                  const intensity = point.count / maxCount;
                  const color = getBubbleColor(intensity);
                  return (
                    <div key={point.label} className="rounded-xl border border-white/10 bg-white/[0.03] p-3 hover:bg-white/[0.05] transition-colors">
                      <div className="flex items-center justify-between text-sm mb-2">
                        <span className="font-semibold text-white/90">{point.label}</span>
                        <span className="text-white font-mono bg-white/10 px-2 py-0.5 rounded-md">{point.count}</span>
                      </div>
                      <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-1000 ease-out"
                          style={{ width: `${Math.max(intensity * 100, 4)}%`, backgroundColor: color }}
                        />
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="h-full min-h-[180px] flex items-center justify-center text-sm text-gray-500 text-center px-4">
                  No matching location data available for the heatmap yet.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default HeatMap;
