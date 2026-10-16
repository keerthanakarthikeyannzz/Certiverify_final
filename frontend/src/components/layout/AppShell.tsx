"use client";
import React, { useState } from "react";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";

interface AppShellProps {
  children: React.ReactNode;
}

export const AppShell: React.FC<AppShellProps> = ({ children }) => {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex font-sans">
      {/* 288px Desktop Sidebar / Mobile Drawer */}
      <Sidebar
        isOpen={mobileSidebarOpen}
        onClose={() => setMobileSidebarOpen(false)}
      />

      {/* Main Content Area Offset by 288px on Desktop */}
      <div className="flex-1 flex flex-col min-w-0 lg:pl-[288px] min-h-screen">
        {/* 64px Top Header */}
        <Header onOpenMobileSidebar={() => setMobileSidebarOpen(true)} />

        {/* Page Content Container */}
        <main className="flex-1 min-w-0 bg-slate-50 p-4 sm:p-6 lg:p-8">
          {children}
        </main>
      </div>
    </div>
  );
};

export default AppShell;
