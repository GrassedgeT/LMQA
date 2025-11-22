import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { authAPI } from '../api';
import './Auth.css';

interface RegisterProps {
  onRegister: () => void;
}

export default function Register({ onRegister }: RegisterProps) {
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await authAPI.register(username, email, password);
      // 注册成功后自动登录
      await authAPI.login(username, password);
      onRegister();
      navigate('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : '注册失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-box">
        <h1>注册</h1>
        {error && <div className="error-message">{error}</div>}
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>用户名</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              minLength={3}
              maxLength={50}
              placeholder="3-50个字符"
            />
          </div>
          <div className="form-group">
            <label>邮箱</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="输入邮箱地址"
            />
          </div>
          <div className="form-group">
            <label>密码</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              placeholder="至少8个字符"
            />
          </div>
          <button type="submit" disabled={loading} className="submit-btn">
            {loading ? '注册中...' : '注册'}
          </button>
        </form>
        <div className="auth-footer">
          已有账号？<Link to="/login">立即登录</Link>
        </div>
      </div>
    </div>
  );
}

