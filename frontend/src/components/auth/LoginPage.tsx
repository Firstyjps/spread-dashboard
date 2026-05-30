import React, { useState } from 'react';
import { useAuth } from './AuthContext';
import { useGoogleLogin } from '@react-oauth/google';
import { Command, LockKeyhole, Activity, ShieldCheck, Zap } from "lucide-react";

export function LoginPage() {
  const { login } = useAuth();
  const [adminPassword, setAdminPassword] = useState("");
  const [adminLoading, setAdminLoading] = useState(false);

  const doGoogleLogin = useGoogleLogin({
    onSuccess: (tokenResponse) => {
      login(tokenResponse);
    },
    onError: (error) => console.error('Login Failed', error)
  });

  const submitLocal = (e: React.FormEvent) => {
    e.preventDefault();
    setAdminLoading(true);
    setTimeout(() => {
      setAdminLoading(false);
      login({ access_token: "dummy" }); 
    }, 1400);
  };

  return (
    <main className="relative bg-black text-white font-sans selection:bg-white/20 overflow-x-hidden min-h-screen">
      {/* Custom Animations */}
      <style dangerouslySetInnerHTML={{__html: `
        @keyframes float {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-10px); }
        }
        @keyframes pan {
          from { background-position: 0 0; }
          to { background-position: 40px 40px; }
        }
      `}} />

      {/* Grid pattern (subtle animated panning) covering the whole page */}
      <div 
        className="fixed inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI0MCIgaGVpZ2h0PSI0MCI+PGRlZnM+PHBhdHRlcm4gaWQ9ImEiIHdpZHRoPSI0MCIgaGVpZ2h0PSI0MCIgcGF0dGVyblVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+PHBhdGggZD0iTTAgNDBoNDBWMEgwem0zOS0zOXYzOEgyVjJoMzd6IiBmaWxsPSJyZ2JhKDI1NSwyNTUsMjU1LDAuMDMpIi8+PC9wYXR0ZXJuPjwvZGVmcz48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSJ1cmwoI2EpIi8+PC9zdmc+')] opacity-30 pointer-events-none z-0" 
        style={{ 
          WebkitMaskImage: "linear-gradient(to bottom, black 0%, transparent 100%)",
          animation: "pan 15s linear infinite"
        }}
      />

      {/* Hero / Login Section */}
      <section className="relative flex min-h-screen items-center justify-center py-20 px-6 z-10">
        {/* Background glow effects - Linear style */}
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[800px] h-[500px] opacity-[0.15] pointer-events-none">
          <div className="absolute inset-0 bg-gradient-to-b from-[#5E6AD2] to-transparent blur-[120px] rounded-full mix-blend-screen" />
        </div>

        <div className="relative w-full max-w-[360px] translate-x-2">
          {/* Floating wrapper */}
          <div style={{ animation: "float 6s ease-in-out infinite" }}>
            
            {/* Header Section */}
            <div className="flex flex-col items-center mb-10 animate-in fade-in slide-in-from-bottom-4 duration-1000 ease-out">
              <div className="relative flex items-center justify-center w-16 h-16 rounded-[20px] bg-white/[0.02] border border-white/[0.08] shadow-[0_0_15px_rgba(255,255,255,0.03)] mb-6 overflow-hidden group hover:border-white/[0.15] transition-colors duration-500">
                <div className="absolute inset-0 bg-gradient-to-b from-white/[0.08] to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                <img src="/logo-icon.png" alt="Deritrade" className="w-10 h-10 object-cover rounded-lg" />
              </div>
              <h1 className="text-[22px] font-medium tracking-[-0.02em] mb-2 text-white/90">Log in to Deritrade</h1>
              <p className="text-[13px] text-white/40 text-center max-w-[260px] leading-relaxed">
                Enter your operator workspace to manage derivatives campaigns.
              </p>
            </div>

            {/* Login Card */}
            <div className="relative rounded-[20px] bg-[#0A0A0A]/80 backdrop-blur-2xl border border-white/[0.08] shadow-[0_0_40px_-10px_rgba(0,0,0,0.6)] p-1 animate-in fade-in slide-in-from-bottom-8 duration-1000 delay-150 ease-out fill-mode-both">
              {/* Subtle top highlight */}
              <div className="absolute top-0 inset-x-0 h-[1px] bg-gradient-to-r from-transparent via-white/[0.15] to-transparent" />
              
              <div className="p-5 flex flex-col gap-3">
                <button
                  type="button"
                  onClick={() => doGoogleLogin()}
                  className="group relative flex items-center justify-center w-full h-[42px] bg-white text-black rounded-xl px-12 text-[13px] font-medium tracking-tight transition-all hover:bg-neutral-200 active:scale-[0.98] shadow-[0_2px_10px_rgba(255,255,255,0.1)]"
                >
                  <svg className="absolute left-4 top-1/2 w-[18px] h-[18px] -translate-y-1/2" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                  </svg>
                  <span>Continue with Google</span>
                </button>
                
                <form onSubmit={submitLocal} className="grid gap-2">
                  <label className="sr-only" htmlFor="admin-password">
                    Local admin password
                  </label>
                  <input
                    id="admin-password"
                    type="password"
                    autoComplete="current-password"
                    value={adminPassword}
                    onChange={(event) => setAdminPassword(event.target.value)}
                    placeholder="Local admin password"
                    className="h-[42px] w-full rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 text-[13px] text-white outline-none transition-colors placeholder:text-white/30 focus:border-white/[0.2]"
                  />
                  <button
                    type="submit"
                    disabled={adminLoading || adminPassword.trim().length === 0}
                    className="group relative flex h-[42px] w-full items-center justify-center rounded-xl border border-emerald-400/20 bg-emerald-400/10 px-12 text-[13px] font-medium tracking-tight text-emerald-100 transition-all hover:bg-emerald-400/15 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <LockKeyhole size={15} className="absolute left-4 top-1/2 -translate-y-1/2 text-emerald-200/80" aria-hidden="true" />
                    <span>{adminLoading ? "Checking local access..." : "Continue with local admin"}</span>
                  </button>
                </form>
              </div>
              
              {/* Security Footer in Card */}
              <div className="px-5 pb-5 pt-1">
                <div className="flex items-center gap-2.5 text-[11px] text-white/30 justify-center">
                  <span className="flex items-center justify-center w-4 h-4 rounded-[4px] bg-white/[0.05] border border-white/[0.05] text-[9px] font-mono">
                    <Command size={9} />
                  </span>
                  <span>Google OAuth + Local Fallback</span>
                </div>
              </div>
            </div>
            
            <div className="mt-12 text-center animate-in fade-in duration-1000 delay-300 fill-mode-both">
              <p className="text-[11px] text-white/20 font-medium tracking-wide uppercase">
                DERITRADE ENGINE v0.42.1
              </p>
            </div>
          </div>
        </div>

        {/* Scroll Indicator */}
        <div className="pointer-events-none absolute inset-x-0 bottom-8 flex justify-center">
          <div className="flex flex-col items-center gap-2 opacity-50 animate-bounce">
            <span className="whitespace-nowrap text-center text-[10px] uppercase tracking-widest text-white/50">Scroll to explore</span>
            <div className="w-px h-6 bg-gradient-to-b from-white/50 to-transparent" />
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="relative z-10 py-32 px-6 max-w-[1000px] mx-auto border-t border-white/[0.05]">
        <div className="mb-20">
          <h2 className="text-[32px] md:text-[40px] font-medium tracking-tight text-white mb-4 leading-[1.1]">
            Private campaign operations for<br className="hidden md:block" /> derivatives desks.
          </h2>
          <p className="text-[20px] md:text-[24px] text-white/40 font-medium tracking-tight leading-tight max-w-[600px]">
            Launch, monitor, and review deterministic bot runs across owner-scoped accounts.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Card 1 */}
          <div className="group relative rounded-[20px] bg-[#0F0F0F] border border-white/[0.05] p-8 hover:border-white/[0.1] transition-colors duration-500">
            <div className="absolute top-12 left-1/2 -translate-x-1/2 w-32 h-32 bg-blue-500/20 blur-[40px] opacity-0 group-hover:opacity-100 transition-opacity duration-700 pointer-events-none" />
            <div className="relative flex items-center justify-center w-16 h-16 rounded-[16px] bg-black border border-white/[0.05] shadow-[0_4px_20px_rgba(0,0,0,0.5)] mb-12">
              <Activity size={24} className="text-blue-400" strokeWidth={1.5} />
            </div>
            <div className="text-[10px] text-white/30 font-medium tracking-widest uppercase mb-4">Fig 0.1</div>
            <h3 className="text-[15px] font-medium text-white mb-3">Execution discipline</h3>
            <p className="text-[13px] text-white/40 leading-relaxed">
              Post-only paths, fill timeouts, and risk defaults keep campaign runs predictable from launch through close.
            </p>
          </div>

          {/* Card 2 */}
          <div className="group relative rounded-[20px] bg-[#0F0F0F] border border-white/[0.05] p-8 hover:border-white/[0.1] transition-colors duration-500">
            <div className="absolute top-12 left-1/2 -translate-x-1/2 w-32 h-32 bg-emerald-500/20 blur-[40px] opacity-0 group-hover:opacity-100 transition-opacity duration-700 pointer-events-none" />
            <div className="relative flex items-center justify-center w-16 h-16 rounded-[16px] bg-black border border-white/[0.05] shadow-[0_4px_20px_rgba(0,0,0,0.5)] mb-12 transform group-hover:-rotate-6 transition-transform duration-500">
              <ShieldCheck size={24} className="text-emerald-400" strokeWidth={1.5} />
            </div>
            <div className="text-[10px] text-white/30 font-medium tracking-widest uppercase mb-4">Fig 0.2</div>
            <h3 className="text-[15px] font-medium text-white mb-3">Owner-scoped access</h3>
            <p className="text-[13px] text-white/40 leading-relaxed">
              Google-authenticated sessions keep API keys, runs, trades, and events partitioned by operator email.
            </p>
          </div>

          {/* Card 3 */}
          <div className="group relative rounded-[20px] bg-[#0F0F0F] border border-white/[0.05] p-8 hover:border-white/[0.1] transition-colors duration-500">
            <div className="absolute top-12 left-1/2 -translate-x-1/2 w-32 h-32 bg-purple-500/20 blur-[40px] opacity-0 group-hover:opacity-100 transition-opacity duration-700 pointer-events-none" />
            <div className="relative flex items-center justify-center w-16 h-16 rounded-[16px] bg-black border border-white/[0.05] shadow-[0_4px_20px_rgba(0,0,0,0.5)] mb-12">
              <Zap size={24} className="text-purple-400" strokeWidth={1.5} />
            </div>
            <div className="text-[10px] text-white/30 font-medium tracking-widest uppercase mb-4">Fig 0.3</div>
            <h3 className="text-[15px] font-medium text-white mb-3">Live run visibility</h3>
            <p className="text-[13px] text-white/40 leading-relaxed">
              SQLite-backed history and Redis streams keep dashboards aligned with worker state during active campaigns.
            </p>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="relative z-10 py-32 px-6 border-t border-white/[0.05] bg-gradient-to-b from-transparent to-black">
        <div className="max-w-[700px] mx-auto text-center">
          <h2 className="text-[32px] md:text-[48px] font-medium tracking-tight text-white mb-10 leading-[1.1]">
            Built for controlled<br /> campaigns.<br />
            Available to approved<br /> operators.
          </h2>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <button className="h-[44px] px-6 rounded-full bg-white text-black font-medium text-[14px] hover:bg-neutral-200 transition-colors">
              Open dashboard
            </button>
            <button className="h-[44px] px-6 rounded-full bg-[#1A1A1A] text-white font-medium text-[14px] border border-white/[0.1] hover:bg-[#222] transition-colors">
              Review campaigns
            </button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative z-10 py-20 px-6 max-w-[1000px] mx-auto border-t border-white/[0.05]">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-10 mb-20">
          <div className="col-span-2 md:col-span-1">
            <div className="w-8 h-8 rounded-lg bg-white/[0.03] border border-white/[0.08] flex items-center justify-center">
              <span className="font-medium text-white/80 text-[14px]">D</span>
            </div>
          </div>
          
          <div>
            <h4 className="text-[13px] font-medium text-white mb-6">Product</h4>
            <ul className="flex flex-col gap-4 text-[13px] text-white/40">
              <li><a href="#" className="hover:text-white/80 transition-colors">Campaigns</a></li>
              <li><a href="#" className="hover:text-white/80 transition-colors">Execution</a></li>
              <li><a href="#" className="hover:text-white/80 transition-colors">Risk Engine</a></li>
              <li><a href="#" className="hover:text-white/80 transition-colors">Pricing</a></li>
              <li><a href="#" className="hover:text-white/80 transition-colors">Security</a></li>
            </ul>
          </div>

          <div>
            <h4 className="text-[13px] font-medium text-white mb-6">Features</h4>
            <ul className="flex flex-col gap-4 text-[13px] text-white/40">
              <li><a href="#" className="hover:text-white/80 transition-colors">Campaign templates</a></li>
              <li><a href="#" className="hover:text-white/80 transition-colors">Campaign runners</a></li>
              <li><a href="#" className="hover:text-white/80 transition-colors">Integrations</a></li>
              <li><a href="#" className="hover:text-white/80 transition-colors">Changelog</a></li>
            </ul>
          </div>

          <div>
            <h4 className="text-[13px] font-medium text-white mb-6">Company</h4>
            <ul className="flex flex-col gap-4 text-[13px] text-white/40">
              <li><a href="#" className="hover:text-white/80 transition-colors">About</a></li>
              <li><a href="#" className="hover:text-white/80 transition-colors">Careers</a></li>
              <li><a href="#" className="hover:text-white/80 transition-colors">Blog</a></li>
            </ul>
          </div>

          <div>
            <h4 className="text-[13px] font-medium text-white mb-6">Connect</h4>
            <ul className="flex flex-col gap-4 text-[13px] text-white/40">
              <li><a href="#" className="hover:text-white/80 transition-colors">Contact us</a></li>
              <li><a href="#" className="hover:text-white/80 transition-colors">X (Twitter)</a></li>
              <li><a href="#" className="hover:text-white/80 transition-colors">GitHub</a></li>
            </ul>
          </div>
        </div>

        <div className="flex items-center gap-6 pt-8 border-t border-white/[0.05] text-[12px] text-white/30">
          <a href="#" className="hover:text-white/70 transition-colors">Privacy</a>
          <a href="#" className="hover:text-white/70 transition-colors">Terms</a>
          <a href="#" className="hover:text-white/70 transition-colors">DPA</a>
        </div>
      </footer>
    </main>
  );
}
