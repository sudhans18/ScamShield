import React, { useEffect, useState } from 'react';

const StatCard = ({ title, value, icon, type, loading }) => {
  // Simple animation for the number
  const [displayValue, setDisplayValue] = useState(0);

  useEffect(() => {
    if (loading || value === undefined) return;
    
    // Animate from 0 to value over 1 second
    const duration = 1000;
    const steps = 30;
    const stepTime = Math.abs(Math.floor(duration / steps));
    let currentStep = 0;
    
    const isNumber = typeof value === 'number';
    const targetValue = isNumber ? value : parseFloat(value.toString().replace(/[^0-9.-]+/g,""));

    if (isNaN(targetValue)) {
      setDisplayValue(value);
      return;
    }

    const timer = setInterval(() => {
      currentStep++;
      const progress = currentStep / steps;
      // Easing function for smooth stop
      const easeOutQuart = 1 - Math.pow(1 - progress, 4);
      const currentVal = Math.floor(targetValue * easeOutQuart);
      
      setDisplayValue(isNumber ? currentVal : currentVal + "+");
      
      if (currentStep >= steps) {
        setDisplayValue(value);
        clearInterval(timer);
      }
    }, stepTime);
    
    return () => clearInterval(timer);
  }, [value, loading]);

  const colors = {
    danger: 'text-danger bg-danger/10 border-danger/20',
    warning: 'text-warning bg-warning/10 border-warning/20',
    primary: 'text-primary bg-primary/10 border-primary/20',
    success: 'text-secondary bg-secondary/10 border-secondary/20',
  };

  const getTheme = () => colors[type] || colors.primary;

  return (
    <div className="glassmorphism rounded-2xl p-6 relative overflow-hidden group hover:border-white/20 transition-all duration-300">
      <div className="absolute -right-6 -top-6 w-24 h-24 rounded-full bg-white/5 blur-2xl group-hover:bg-white/10 transition-colors" />
      
      <div className="flex justify-between items-start mb-4 relative z-10">
        <h3 className="text-gray-400 font-medium text-sm">{title}</h3>
        <div className={`p-2 rounded-lg border ${getTheme()}`}>
          {icon}
        </div>
      </div>
      
      <div className="relative z-10">
        {loading ? (
          <div className="h-8 w-24 bg-white/10 rounded animate-pulse" />
        ) : (
          <h2 className="text-3xl font-bold text-white tracking-tight">
            {typeof displayValue === 'number' ? displayValue.toLocaleString() : displayValue}
          </h2>
        )}
      </div>
    </div>
  );
};

export default StatCard;
