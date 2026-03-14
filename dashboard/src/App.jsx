import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import { ShieldAlert, Search, LayoutDashboard } from 'lucide-react';
import Dashboard from './pages/Dashboard';
import PhoneLookup from './pages/PhoneLookup';

const NavLink = ({ to, icon, label }) => {
  const location = useLocation();
  const isActive = location.pathname === to;
  return (
    <Link
      to={to}
      className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
        isActive ? 'bg-primary/20 text-primary border border-primary/30' : 'text-gray-400 hover:bg-white/5 hover:text-white'
      }`}
    >
      {icon}
      <span className="font-medium">{label}</span>
    </Link>
  );
};

const Layout = ({ children }) => {
  return (
    <div className="flex bg-background min-h-screen text-gray-100 font-sans">
      {/* Sidebar */}
      <aside className="w-64 border-r border-white/5 bg-card/50 backdrop-blur-xl flex flex-col hidden md:flex">
        <div className="p-6 flex items-center gap-3">
          <ShieldAlert className="w-8 h-8 text-danger" />
          <h1 className="text-xl font-bold tracking-tight text-white">Scam<span className="text-danger">Shield</span></h1>
        </div>
        <nav className="flex-1 px-4 py-6 space-y-2">
          <NavLink to="/" icon={<LayoutDashboard className="w-5 h-5" />} label="Dashboard" />
          <NavLink to="/lookup" icon={<Search className="w-5 h-5" />} label="Phone Lookup" />
        </nav>
        <div className="p-6 border-t border-white/5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-primary to-secondary flex items-center justify-center font-bold text-white shadow-lg">
              A
            </div>
            <div>
              <p className="text-sm font-medium text-white">Admin User</p>
              <p className="text-xs text-gray-500">Security Dept</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col min-h-screen overflow-hidden">
        {/* Mobile Header */}
        <header className="md:hidden flex items-center justify-between p-4 border-b border-white/5 bg-card">
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-6 h-6 text-danger" />
            <span className="font-bold">ScamShield</span>
          </div>
          <div className="flex gap-4 text-sm font-medium">
            <Link to="/" className="text-primary">Dashboard</Link>
            <Link to="/lookup" className="text-gray-400">Lookup</Link>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-4 md:p-8">
          <div className="max-w-7xl mx-auto">
            {children}
          </div>
        </div>
      </main>
    </div>
  );
};

function App() {
  return (
    <Router>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/lookup" element={<PhoneLookup />} />
        </Routes>
      </Layout>
    </Router>
  );
}

export default App;
