import { useState, useEffect } from 'react';
import { memoryAPI } from '../api';
import { handleError } from '../utils';
import HighlightText from '../components/HighlightText';
import './MemoryPage.css';

interface Memory {
  id: number;
  title: string;
  content: string;
  category?: string;
  tags?: string;
  memory_type?: string;
  created_at: string;
  updated_at: string;
}

export default function MemoryPage() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [showEditor, setShowEditor] = useState(false);
  const [editingMemory, setEditingMemory] = useState<Memory | null>(null);
  const [formData, setFormData] = useState({
    title: '',
    content: '',
    category: '',
    tags: '',
  });

  useEffect(() => {
    loadMemories();
  }, [search, category]);

  const loadMemories = async () => {
    try {
      setLoading(true);
      const data = await memoryAPI.getMemories(1, 50, category || undefined, search || undefined);
      setMemories(data.memories);
    } catch (err) {
      handleError(err, '加载记忆失败');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = () => {
    setEditingMemory(null);
    setFormData({ title: '', content: '', category: '', tags: '' });
    setShowEditor(true);
  };

  const handleEdit = (memory: Memory) => {
    setEditingMemory(memory);
    setFormData({
      title: memory.title,
      content: memory.content,
      category: memory.category || '',
      tags: typeof memory.tags === 'string' ? memory.tags : '',
    });
    setShowEditor(true);
  };

  const handleSave = async () => {
    try {
      const memoryData = {
        title: formData.title,
        content: formData.content,
        category: formData.category || undefined,
        tags: formData.tags ? formData.tags.split(',').map((t) => t.trim()) : undefined,
      };
      if (editingMemory) {
        await memoryAPI.updateMemory(editingMemory.id, memoryData);
      } else {
        await memoryAPI.createMemory(memoryData);
      }
      setShowEditor(false);
      await loadMemories();
    } catch (err) {
      handleError(err, '保存失败');
    }
  };

  const handleDelete = async (memoryId: number) => {
    if (!confirm('确定要删除这个记忆吗？')) return;
    try {
      await memoryAPI.deleteMemory(memoryId);
      await loadMemories();
    } catch (err) {
      handleError(err, '删除失败');
    }
  };

  return (
    <div className="memory-page">
      <div className="memory-header">
        <h1>记忆管理</h1>
        <button onClick={handleCreate} className="create-btn">
          <span>+</span>
          <span>新建记忆</span>
        </button>
      </div>
      <div className="memory-filters">
        <input
          type="text"
          placeholder="搜索记忆..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="search-input"
        />
        <select value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">全部分类</option>
          <option value="工作">工作</option>
          <option value="学习">学习</option>
          <option value="生活">生活</option>
          <option value="其他">其他</option>
        </select>
      </div>
      {loading ? (
        <div style={{ textAlign: 'center', color: '#94a3b8', padding: '60px 0' }}>
          <div style={{ fontSize: '24px', marginBottom: '12px' }}>⏳</div>
          <div>加载中...</div>
        </div>
      ) : (
        <div className="memory-list">
          {memories.length === 0 ? (
            <div style={{ 
              gridColumn: '1 / -1', 
              textAlign: 'center', 
              color: '#94a3b8', 
              padding: '80px 20px',
              fontSize: '16px'
            }}>
              <div style={{ fontSize: '64px', marginBottom: '16px', opacity: 0.5 }}>📝</div>
              <div>暂无记忆</div>
              <div style={{ marginTop: '8px', fontSize: '14px', opacity: 0.7 }}>点击上方"新建记忆"按钮创建第一个记忆</div>
            </div>
          ) : (
            memories.map((memory) => (
              <div key={memory.id} className="memory-card">
                <div className="memory-header-card">
                  <h3>
                    <HighlightText text={memory.title} highlight={search} />
                  </h3>
                  <div className="memory-actions">
                    <button onClick={() => handleEdit(memory)}>编辑</button>
                    <button onClick={() => handleDelete(memory.id)} className="delete-btn">
                      删除
                    </button>
                  </div>
                </div>
                <div className="memory-content">
                  <HighlightText 
                    text={memory.content.length > 200 ? memory.content.substring(0, 200) + '...' : memory.content} 
                    highlight={search} 
                  />
                </div>
                {memory.category && (
                  <div className="memory-meta">
                    <span className="category">分类: {memory.category}</span>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}
      {showEditor && (
        <div className="modal-overlay" onClick={() => setShowEditor(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2>{editingMemory ? '编辑记忆' : '新建记忆'}</h2>
            <div className="form-group">
              <label>标题</label>
              <input
                type="text"
                value={formData.title}
                onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                placeholder="输入标题"
              />
            </div>
            <div className="form-group">
              <label>内容</label>
              <textarea
                value={formData.content}
                onChange={(e) => setFormData({ ...formData, content: e.target.value })}
                placeholder="输入内容"
                rows={5}
              />
            </div>
            <div className="form-group">
              <label>分类</label>
              <input
                type="text"
                value={formData.category}
                onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                placeholder="输入分类（可选）"
              />
            </div>
            <div className="form-group">
              <label>标签（逗号分隔）</label>
              <input
                type="text"
                value={formData.tags}
                onChange={(e) => setFormData({ ...formData, tags: e.target.value })}
                placeholder="输入标签，用逗号分隔"
              />
            </div>
            <div className="modal-actions">
              <button onClick={() => setShowEditor(false)}>取消</button>
              <button onClick={handleSave} className="save-btn">
                保存
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

