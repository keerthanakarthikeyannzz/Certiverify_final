"use client";

import React from 'react';
import { AIWorkspaceProvider, useAIWorkspace } from '../../context/AIWorkspaceContext';
import { AIHeader } from './AIHeader';
import { AISidebar } from './AISidebar';
import { AIChatWorkspace } from './AIChatWorkspace';
import { AIContextPanel } from './AIContextPanel';
import { AIArtifactViewer } from './AIArtifactViewer';
import { AISettingsModal } from './AISettingsModal';
import { NotificationsPanel } from './NotificationsPanel';

// Dedicated Workspace Views
import { DashboardView } from './views/DashboardView';
import { CertificatesView } from './views/CertificatesView';
import { UploadView } from './views/UploadView';
import { PipelineView } from './views/PipelineView';
import { CockpitView } from './views/CockpitView';
import { CertificateDetailView } from './views/CertificateDetailView';
import { EvidenceExplorerView } from './views/EvidenceExplorerView';
import { InvestigationView } from './views/InvestigationView';
import { CompareView } from './views/CompareView';
import { AISearchView } from './views/AISearchView';
import { ReportsView } from './views/ReportsView';
import { HistoryView } from './views/HistoryView';
import { ReviewView } from './views/ReviewView';

export const AIWorkspaceContent: React.FC = () => {
  const { activeView } = useAIWorkspace();

  const renderActiveView = () => {
    switch (activeView) {
      case 'dashboard':
        return <DashboardView />;
      case 'certificates':
        return <CertificatesView />;
      case 'upload':
        return <UploadView />;
      case 'pipeline':
        return <PipelineView />;
      case 'cockpit':
        return <CockpitView />;
      case 'detail':
        return <CertificateDetailView />;
      case 'evidence':
        return <EvidenceExplorerView />;
      case 'investigation':
        return <InvestigationView />;
      case 'compare':
        return <CompareView />;
      case 'search':
        return <AISearchView />;
      case 'reports':
        return <ReportsView />;
      case 'history':
        return <HistoryView />;
      case 'review':
        return <ReviewView />;
      case 'chat':
      default:
        return (
          <div className="flex-1 h-full flex overflow-hidden">
            {/* CENTER: Flexible AI Conversation Workspace */}
            <AIChatWorkspace />
            {/* RIGHT: 360px Context / Evidence / Document Panel */}
            <AIContextPanel />
          </div>
        );
    }
  };

  return (
    <div className="w-screen h-screen bg-[#fafafa] flex flex-col overflow-hidden font-sans text-slate-900 select-none antialiased">
      {/* Global Minimal Top Header */}
      <AIHeader />

      {/* Main 3-Column Desktop Layout Body */}
      <div className="flex-1 flex overflow-hidden">
        {/* LEFT: 280px AI Navigation & History Sidebar */}
        <AISidebar />

        {/* Dynamic Center / Right Workspace View */}
        {renderActiveView()}
      </div>

      {/* Claude-style Artifact Report Viewer */}
      <AIArtifactViewer />

      {/* Settings Configuration Modal */}
      <AISettingsModal />

      {/* Activity Notifications Panel Drawer */}
      <NotificationsPanel />
    </div>
  );
};

export const AIWorkspace: React.FC = () => {
  return (
    <AIWorkspaceProvider>
      <AIWorkspaceContent />
    </AIWorkspaceProvider>
  );
};
