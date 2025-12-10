import { useState, type FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { authAPI } from '../api';
import './Auth.css';

interface RegisterProps {
  onRegister: () => void;
}

/**
 * 注册页面组件
 */
export default function Register({ onRegister }: RegisterProps) {
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError('');
    
    // 表单验证
    if (!username.trim() || username.trim().length < 3) {
      setError('用户名至少需要3个字符');
      return;
    }
    
    if (!email.trim() || !email.includes('@')) {
      setError('请输入有效的邮箱地址');
      return;
    }
    
    if (!password || password.length < 8) {
      setError('密码至少需要8个字符');
      return;
    }
    
    setLoading(true);

    try {
      await authAPI.register(username.trim(), email.trim(), password);
      // 注册成功后自动登录
      await authAPI.login(username.trim(), password);
      onRegister();
      navigate('/', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : '注册失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  const handleFieldChange = () => {
    if (error) setError(''); // 清除错误信息
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
              onChange={(e) => {
                setUsername(e.target.value);
                handleFieldChange();
              }}
              required
              minLength={3}
              maxLength={50}
              placeholder="3-50个字符"
              autoComplete="username"
              disabled={loading}
            />
          </div>
          <div className="form-group">
            <label>邮箱</label>
            <input
              type="email"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                handleFieldChange();
              }}
              required
              placeholder="输入邮箱地址"
              autoComplete="email"
              disabled={loading}
            />
          </div>
          <div className="form-group">
            <label>密码</label>
            <input
              type="password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                handleFieldChange();
              }}
              required
              minLength={8}
              placeholder="至少8个字符"
              autoComplete="new-password"
              disabled={loading}
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

