import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../../services/api';
import { Key, Shield, User, Bot, Save, Activity } from 'lucide-react';

export function SettingsPage() {
  const queryClient = useQueryClient();
  
  const [formData, setFormData] = useState({
    bybit_api_key: '',
    bybit_api_secret: '',
    lighter_api_public_key: '',
    lighter_api_private_key: '',
    lighter_private_key: '',
    ai_bybit_api_key: '',
    ai_bybit_api_secret: '',
    ai_lighter_api_public_key: '',
    ai_lighter_api_private_key: '',
    ai_lighter_private_key: ''
  });

  const { data: keys, isLoading } = useQuery({
    queryKey: ['apiKeys'],
    queryFn: async () => {
      try {
        return await api.getApiKeys();
      } catch (e) {
        // Fallback for local preview if backend is off
        return {
          bybit_api_key: '***',
          bybit_api_secret: '***',
          lighter_api_public_key: '***',
          lighter_api_private_key: '***',
          lighter_private_key: '***',
          ai_bybit_api_key: '',
          ai_bybit_api_secret: '',
          ai_lighter_api_public_key: '',
          ai_lighter_api_private_key: '',
          ai_lighter_private_key: ''
        };
      }
    }
  });

  const updateMutation = useMutation({
    mutationFn: api.updateApiKeys,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['apiKeys'] });
      alert("Settings saved successfully! The backend has been reloaded.");
      setFormData({
        bybit_api_key: '',
        bybit_api_secret: '',
        lighter_api_public_key: '',
        lighter_api_private_key: '',
        lighter_private_key: '',
        ai_bybit_api_key: '',
        ai_bybit_api_secret: '',
        ai_lighter_api_public_key: '',
        ai_lighter_api_private_key: '',
        ai_lighter_private_key: ''
      });
    },
    onError: () => {
      alert("Failed to save settings. Make sure backend is running.");
    }
  });

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSave = () => {
    // Filter out empty fields so we don't overwrite existing keys with blanks
    const updates: any = {};
    Object.entries(formData).forEach(([k, v]) => {
      if (v.trim() !== '') updates[k] = v;
    });
    
    if (Object.keys(updates).length > 0) {
      updateMutation.mutate(updates);
    }
  };

  if (isLoading) {
    return <div className="p-6 text-gray-500 flex items-center gap-2"><Activity className="animate-spin" size={16}/> Loading Settings...</div>;
  }

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center gap-3">
        <Settings className="text-gray-400" size={32} />
        <div>
          <h1 className="text-2xl font-bold tracking-tight">System Settings</h1>
          <p className="text-sm text-gray-400">Manage your API keys and security credentials securely.</p>
        </div>
      </div>

      {/* Connection Status Overview */}
      <div className="bg-bg1 border border-bd1 rounded-lg p-5">
        <h2 className="font-semibold text-lg border-b border-bd1 pb-3 mb-4 flex items-center gap-2">
          <Activity className="text-green-400" size={20} />
          Current Connection Status
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-bg2 p-4 rounded border border-bd2 flex flex-col gap-2">
            <h3 className="font-medium flex items-center gap-2 text-sm text-gray-300">
              <User size={16} className="text-blue-400" /> Manual Account Status
            </h3>
            <div className="flex justify-between items-center text-sm">
              <span className="text-gray-400">Bybit API:</span>
              {keys?.bybit_api_key ? (
                <span className="text-green-400 font-mono bg-green-400/10 px-2 py-0.5 rounded border border-green-400/20">{keys.bybit_api_key}</span>
              ) : (
                <span className="text-red-400">Not Configured</span>
              )}
            </div>
            <div className="flex justify-between items-center text-sm">
              <span className="text-gray-400">Lighter API Public:</span>
              {keys?.lighter_api_public_key ? (
                <span className="text-green-400 font-mono bg-green-400/10 px-2 py-0.5 rounded border border-green-400/20">{keys.lighter_api_public_key}</span>
              ) : (
                <span className="text-red-400">Not Configured</span>
              )}
            </div>
            <div className="flex justify-between items-center text-sm">
              <span className="text-gray-400">Lighter API Private:</span>
              {keys?.lighter_api_private_key ? (
                <span className="text-green-400 font-mono bg-green-400/10 px-2 py-0.5 rounded border border-green-400/20">{keys.lighter_api_private_key}</span>
              ) : (
                <span className="text-red-400">Not Configured</span>
              )}
            </div>
            <div className="flex justify-between items-center text-sm">
              <span className="text-gray-400">Lighter EVM Key:</span>
              {keys?.lighter_private_key ? (
                <span className="text-green-400 font-mono bg-green-400/10 px-2 py-0.5 rounded border border-green-400/20">{keys.lighter_private_key}</span>
              ) : (
                <span className="text-red-400">Not Configured</span>
              )}
            </div>
          </div>

          <div className="bg-bg2 p-4 rounded border border-bd2 flex flex-col gap-2">
            <h3 className="font-medium flex items-center gap-2 text-sm text-gray-300">
              <Bot size={16} className="text-purple-400" /> AI Trading Status
            </h3>
            <div className="flex justify-between items-center text-sm">
              <span className="text-gray-400">Bybit API:</span>
              {keys?.ai_bybit_api_key ? (
                <span className="text-green-400 font-mono bg-green-400/10 px-2 py-0.5 rounded border border-green-400/20">{keys.ai_bybit_api_key}</span>
              ) : (
                <span className="text-red-400">Not Configured</span>
              )}
            </div>
            <div className="flex justify-between items-center text-sm">
              <span className="text-gray-400">Lighter API Public:</span>
              {keys?.ai_lighter_api_public_key ? (
                <span className="text-green-400 font-mono bg-green-400/10 px-2 py-0.5 rounded border border-green-400/20">{keys.ai_lighter_api_public_key}</span>
              ) : (
                <span className="text-red-400">Not Configured</span>
              )}
            </div>
            <div className="flex justify-between items-center text-sm">
              <span className="text-gray-400">Lighter API Private:</span>
              {keys?.ai_lighter_api_private_key ? (
                <span className="text-green-400 font-mono bg-green-400/10 px-2 py-0.5 rounded border border-green-400/20">{keys.ai_lighter_api_private_key}</span>
              ) : (
                <span className="text-red-400">Not Configured</span>
              )}
            </div>
            <div className="flex justify-between items-center text-sm">
              <span className="text-gray-400">Lighter EVM Key:</span>
              {keys?.ai_lighter_private_key ? (
                <span className="text-green-400 font-mono bg-green-400/10 px-2 py-0.5 rounded border border-green-400/20">{keys.ai_lighter_private_key}</span>
              ) : (
                <span className="text-red-400">Not Configured</span>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* Manual Trading Credentials */}
        <div className="bg-bg1 border border-bd1 rounded-lg p-5 flex flex-col gap-4">
          <div className="flex items-center gap-2 border-b border-bd1 pb-3">
            <User className="text-blue-400" size={20} />
            <h2 className="font-semibold text-lg">Manual Trading Credentials</h2>
          </div>
          <p className="text-xs text-gray-400">
            These keys are used when you manually execute trades from the Dashboard.
          </p>

          <div className="space-y-3">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Bybit API Key</label>
              <input 
                type="password" 
                name="bybit_api_key"
                placeholder={keys?.bybit_api_key ? "(Configured - Enter new to replace)" : "Enter Bybit API Key"}
                value={formData.bybit_api_key}
                onChange={handleChange}
                className="w-full bg-bg2 border border-bd2 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Bybit API Secret</label>
              <input 
                type="password" 
                name="bybit_api_secret"
                placeholder={keys?.bybit_api_secret ? "(Configured - Enter new to replace)" : "Enter Bybit API Secret"}
                value={formData.bybit_api_secret}
                onChange={handleChange}
                className="w-full bg-bg2 border border-bd2 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
              />
            </div>
            <div className="pt-2">
              <label className="text-xs text-gray-400 mb-1 block">Lighter API Public Key</label>
              <input 
                type="text" 
                name="lighter_api_public_key"
                placeholder={keys?.lighter_api_public_key ? "(Configured - Enter new to replace)" : "Enter Lighter API Public Key"}
                value={formData.lighter_api_public_key}
                onChange={handleChange}
                className="w-full bg-bg2 border border-bd2 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Lighter API Private Key</label>
              <input 
                type="password" 
                name="lighter_api_private_key"
                placeholder={keys?.lighter_api_private_key ? "(Configured - Enter new to replace)" : "Enter Lighter API Private Key"}
                value={formData.lighter_api_private_key}
                onChange={handleChange}
                className="w-full bg-bg2 border border-bd2 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Lighter Private Key (EVM Wallet)</label>
              <input 
                type="password" 
                name="lighter_private_key"
                placeholder={keys?.lighter_private_key ? "(Configured - Enter new to replace)" : "Enter Lighter Private Key"}
                value={formData.lighter_private_key}
                onChange={handleChange}
                className="w-full bg-bg2 border border-bd2 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>
        </div>

        {/* AI Auto-Trade Credentials */}
        <div className="bg-bg1 border border-bd1 rounded-lg p-5 flex flex-col gap-4">
          <div className="flex items-center gap-2 border-b border-bd1 pb-3">
            <Bot className="text-purple-400" size={20} />
            <h2 className="font-semibold text-lg">AI Trading Credentials</h2>
          </div>
          <p className="text-xs text-gray-400">
            These keys are exclusively used by the AI Trading Daemon. It is highly recommended to use a separate sub-account.
          </p>

          <div className="space-y-3">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">AI Bybit API Key</label>
              <input 
                type="password" 
                name="ai_bybit_api_key"
                placeholder={keys?.ai_bybit_api_key ? "(Configured - Enter new to replace)" : "Enter AI Sub-account API Key"}
                value={formData.ai_bybit_api_key}
                onChange={handleChange}
                className="w-full bg-bg2 border border-bd2 rounded px-3 py-2 text-sm focus:outline-none focus:border-purple-500"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">AI Bybit API Secret</label>
              <input 
                type="password" 
                name="ai_bybit_api_secret"
                placeholder={keys?.ai_bybit_api_secret ? "(Configured - Enter new to replace)" : "Enter AI Sub-account API Secret"}
                value={formData.ai_bybit_api_secret}
                onChange={handleChange}
                className="w-full bg-bg2 border border-bd2 rounded px-3 py-2 text-sm focus:outline-none focus:border-purple-500"
              />
            </div>
            <div className="pt-2">
              <label className="text-xs text-gray-400 mb-1 block">AI Lighter API Public Key</label>
              <input 
                type="text" 
                name="ai_lighter_api_public_key"
                placeholder={keys?.ai_lighter_api_public_key ? "(Configured - Enter new to replace)" : "Enter AI Lighter API Public Key"}
                value={formData.ai_lighter_api_public_key}
                onChange={handleChange}
                className="w-full bg-bg2 border border-bd2 rounded px-3 py-2 text-sm focus:outline-none focus:border-purple-500"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">AI Lighter API Private Key</label>
              <input 
                type="password" 
                name="ai_lighter_api_private_key"
                placeholder={keys?.ai_lighter_api_private_key ? "(Configured - Enter new to replace)" : "Enter AI Lighter API Private Key"}
                value={formData.ai_lighter_api_private_key}
                onChange={handleChange}
                className="w-full bg-bg2 border border-bd2 rounded px-3 py-2 text-sm focus:outline-none focus:border-purple-500"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">AI Lighter Private Key (EVM Wallet)</label>
              <input 
                type="password" 
                name="ai_lighter_private_key"
                placeholder={keys?.ai_lighter_private_key ? "(Configured - Enter new to replace)" : "Enter AI Wallet Private Key"}
                value={formData.ai_lighter_private_key}
                onChange={handleChange}
                className="w-full bg-bg2 border border-bd2 rounded px-3 py-2 text-sm focus:outline-none focus:border-purple-500"
              />
            </div>
          </div>
        </div>

      </div>
      
      <div className="flex justify-end pt-4">
        <button 
          onClick={handleSave}
          disabled={updateMutation.isPending}
          className="bg-white text-black hover:bg-gray-200 px-6 py-2.5 rounded-md font-semibold text-sm transition-colors flex items-center gap-2"
        >
          <Save size={16} />
          {updateMutation.isPending ? "Saving..." : "Save API Credentials"}
        </button>
      </div>

    </div>
  );
}

const Settings = ({ className, size }: { className?: string; size?: number }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width={size || 24} height={size || 24} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>
    <circle cx="12" cy="12" r="3"/>
  </svg>
);
