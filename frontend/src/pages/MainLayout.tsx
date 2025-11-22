import { useState } from 'react';
import { Routes, Route, useNavigate } from 'react-router-dom';
import { setAuthToken } from '../api';
import { useTheme } from '../contexts/ThemeContext';
import ChatPage from './ChatPage';
import MemoryPage from './MemoryPage';
import ProfilePage from './ProfilePage';
import './MainLayout.css';

export default function MainLayout() {
  const [activeTab, setActiveTab] = useState<'chat' | 'memory' | 'profile'>('chat');
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();

  const handleLogout = () => {
    setAuthToken(null);
    navigate('/login');
  };

  return (
    <div className="main-layout">
      <div className="sidebar">
        <div className="sidebar-header">
          <h2>LMQA</h2>
        </div>
        <nav className="sidebar-nav">
          <button
            className={activeTab === 'chat' ? 'active' : ''}
            onClick={() => {
              setActiveTab('chat');
              navigate('/');
            }}
          >
            <span>💬</span>
            <span>对话</span>
          </button>
          <button
            className={activeTab === 'memory' ? 'active' : ''}
            onClick={() => {
              setActiveTab('memory');
              navigate('/memories');
            }}
          >
            <span>🧠</span>
            <span>记忆管理</span>
          </button>
          <button
            className={activeTab === 'profile' ? 'active' : ''}
            onClick={() => {
              setActiveTab('profile');
              navigate('/profile');
            }}
          >
            <span>⚙️</span>
            <span>个人设置</span>
          </button>
        </nav>
        <div className="sidebar-footer">
          <button onClick={handleLogout} className="logout-btn">
            退出登录
          </button>
        </div>
      </div>
      <div className="main-content">
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/memories" element={<MemoryPage />} />
          <Route path="/profile" element={<ProfilePage />} />
        </Routes>
      </div>
    </div>
  );
}

