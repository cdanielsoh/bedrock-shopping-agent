import { useState } from 'react';
import ChatBox from './components/ChatBox';
import MonitoringDashboard from './components/MonitoringDashboard';
import './App.css';

type AppView = 'chat' | 'monitoring';

function App() {
  const [currentView, setCurrentView] = useState<AppView>('chat');

  return (
    <div className="App">
      <main>
        {currentView === 'chat' && <ChatBox onViewChange={setCurrentView} />}
        {currentView === 'monitoring' && <MonitoringDashboard onViewChange={setCurrentView} />}
      </main>
    </div>
  );
}

export default App;
