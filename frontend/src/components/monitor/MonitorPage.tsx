import React from 'react';

export function MonitorPage() {
  return (
    <div className="flex flex-col h-full gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Monitor</h1>
        <div className="flex gap-2">
          {/* Controls will go here */}
        </div>
      </div>
      <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-4 auto-rows-min">
        {/* Pair cards will go here */}
        <div className="text-fg3 text-sm">Loading pairs...</div>
      </div>
    </div>
  );
}
