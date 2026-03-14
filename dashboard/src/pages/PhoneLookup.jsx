import React, { useState } from 'react';
import { Search, AlertCircle, ShieldCheck, Phone, MapPin, Building, Link as LinkIcon, Clock } from 'lucide-react';
import { fetchPhoneDetails } from '../services/api';

const PhoneLookup = () => {
  const [phoneNumber, setPhoneNumber] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!phoneNumber.trim()) {
      setError('Please enter a phone number');
      return;
    }
    
    setError('');
    setLoading(true);
    setResult(null);

    try {
      const data = await fetchPhoneDetails(phoneNumber);
      setResult(data);
    } catch (err) {
      setError('Could not fetch details. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const getRiskColor = (score) => {
    switch (score) {
      case 'High Risk': return 'text-danger bg-danger/10 border-danger/20';
      case 'Suspicious': return 'text-warning bg-warning/10 border-warning/20';
      case 'Safe': return 'text-secondary bg-secondary/10 border-secondary/20';
      default: return 'text-gray-400 bg-gray-500/10 border-gray-500/20';
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Phone Number Lookup</h1>
        <p className="text-gray-400 mt-1">Investigate suspicious numbers and view associated scam data</p>
      </div>

      <div className="glassmorphism p-6 rounded-2xl border border-white/10 shadow-xl">
        <form onSubmit={handleSearch} className="flex gap-4">
          <div className="relative flex-1">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
            <input
              type="text"
              placeholder="Enter phone number (e.g. +91 98765 43210)"
              value={phoneNumber}
              onChange={(e) => setPhoneNumber(e.target.value)}
              className="w-full bg-black/20 border border-white/10 rounded-xl py-3 pl-12 pr-4 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="bg-primary hover:bg-primary/90 text-white px-8 py-3 rounded-xl font-medium transition-all shadow-lg shadow-primary/25 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {loading ? (
              <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              'Lookup'
            )}
          </button>
        </form>
        {error && <p className="text-danger mt-3 text-sm flex items-center gap-2"><AlertCircle className="w-4 h-4" />{error}</p>}
      </div>

      {result && (
        <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
          <div className="glassmorphism rounded-2xl overflow-hidden border border-white/10 shadow-2xl">
            <div className={`p-6 border-b border-white/5 flex items-center justify-between ${result.riskScore === 'Safe' ? 'bg-secondary/5' : 'bg-danger/5'}`}>
              <div className="flex items-center gap-4">
                <div className={`w-14 h-14 rounded-full flex items-center justify-center border ${getRiskColor(result.riskScore)}`}>
                  <Phone className="w-6 h-6" />
                </div>
                <div>
                  <h2 className="text-2xl font-bold">{result.number}</h2>
                  <p className="text-gray-400 text-sm flex items-center gap-1.5 mt-1">
                    <Clock className="w-4 h-4" /> Last seen: {result.lastSeen}
                  </p>
                </div>
              </div>
              <div className={`px-4 py-2 rounded-xl border font-bold text-lg flex items-center gap-2 shadow-lg ${getRiskColor(result.riskScore)}`}>
                {result.riskScore === 'Safe' ? <ShieldCheck className="w-5 h-5" /> : <AlertCircle className="w-5 h-5" />}
                {result.riskScore}
              </div>
            </div>

            <div className="p-6 grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="glassmorphism p-5 rounded-xl border border-white/5 bg-black/20">
                <div className="text-gray-400 text-sm mb-2 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4" /> Reports Count
                </div>
                <div className="text-3xl font-bold">{result.reportCount}</div>
              </div>

              <div className="glassmorphism p-5 rounded-xl border border-white/5 bg-black/20">
                <div className="text-gray-400 text-sm mb-3 flex items-center gap-2">
                  <Building className="w-4 h-4" /> Associated Entities
                </div>
                <ul className="space-y-2">
                  {result.companies.map((company, i) => (
                    <li key={i} className="flex items-center gap-2 text-white font-medium">
                      <div className="w-1.5 h-1.5 rounded-full bg-primary" />
                      {company}
                    </li>
                  ))}
                  {result.companies.length === 0 && <li className="text-gray-500 italic">None found</li>}
                </ul>
              </div>

              <div className="glassmorphism p-5 rounded-xl border border-white/5 bg-black/20">
                <div className="text-gray-400 text-sm mb-3 flex items-center gap-2">
                  <LinkIcon className="w-4 h-4" /> Linked UPI IDs
                </div>
                <ul className="space-y-2">
                  {result.upiIds.map((id, i) => (
                    <li key={i} className="flex items-center gap-2 text-danger font-mono text-sm">
                      <div className="w-1.5 h-1.5 rounded-full bg-danger/50" />
                      {id}
                    </li>
                  ))}
                  {result.upiIds.length === 0 && <li className="text-gray-500 italic">None found</li>}
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PhoneLookup;
