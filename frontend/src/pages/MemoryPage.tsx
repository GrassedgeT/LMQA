import { useState, useEffect, useCallback } from 'react';
import { memoryAPI, conversationAPI } from '../api';
import { handleError, debounce } from '../utils';
import HighlightText from '../components/HighlightText';
import './MemoryPage.css';

interface Memory {
  id: number | string;
  title: string;
  content: string;
  category?: string;
  tags?: string;
  memory_type?: string;
  created_at: string;
  updated_at: string;
}

interface Relation {
  source: string;
  target: string;
  relationship: string;
}

interface Conversation {
  id: number;
  title: string;
}

export default function MemoryPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<number>(0); // 0 = Global/All User Memories

  const [memories, setMemories] = useState<Memory[]>([]);
  const [relations, setRelations] = useState<Relation[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');

  // 加载会话列表
  useEffect(() => {
    const fetchConversations = async () => {
      try {
        const data = await conversationAPI.getConversations(1, 100);
        setConversations(data.conversations);
      } catch (err) {
        console.error("Failed to load conversations", err);
      }
    };
    fetchConversations();
  }, []);

  // 使用防抖优化搜索
  const debouncedLoadMemories = useCallback(
    debounce(async (searchValue: string, convId: number) => {
      try {
        setLoading(true);
        // If convId is 0, backend handles as global/user level if run_id is omitted or specifically handled
        // Our updated API sends 'conversation_id' only if not null/undefined. 
        // If we send 0, let's treat it as "Global" (run_id = None).
        
        const data = await memoryAPI.getMemories(convId, 1, 50, undefined, searchValue || undefined);
        setMemories(data.memories);
        setRelations(data.relations || []);
      } catch (err) {
        handleError(err, '加载记忆失败');
      } finally {
        setLoading(false);
      }
    }, 300),
    []
  );

  useEffect(() => {
    debouncedLoadMemories(search, selectedConversationId);
  }, [search, selectedConversationId, debouncedLoadMemories]);

  return (
    <div className="memory-page-container">
      <div className="memory-sidebar">
        <h3>范围选择</h3>
        <div 
          className={`sidebar-item ${selectedConversationId === 0 ? 'active' : ''}`}
          onClick={() => setSelectedConversationId(0)}
        >
          👤 用户全局记忆
        </div>
        <div className="sidebar-divider">对话记忆</div>
        <div className="sidebar-list">
          {conversations.map(c => (
            <div 
              key={c.id} 
              className={`sidebar-item ${selectedConversationId === c.id ? 'active' : ''}`}
              onClick={() => setSelectedConversationId(c.id)}
              title={c.title}
            >
              💬 {c.title || '无标题对话'}
            </div>
          ))}
        </div>
      </div>

      <div className="memory-content-area">
        <div className="memory-header">
          <h2>
            {selectedConversationId === 0 
              ? '用户全局记忆' 
              : `对话记忆: ${conversations.find(c => c.id === selectedConversationId)?.title || '未知对话'}`}
          </h2>
          <div className="memory-search">
            <input
              type="text"
              placeholder="搜索记忆内容..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>

        {loading ? (
          <div className="loading-state">
            <div className="spinner"></div>
            <p>加载记忆图谱与列表...</p>
          </div>
        ) : (
          <div className="memory-display">
            {memories.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">📭</div>
                <p>暂无相关记忆</p>
              </div>
            ) : (
              <>
                <div className="memory-section">
                  <h3>📝 记忆列表 ({memories.length})</h3>
                  <div className="memory-cards">
                    {memories.map((memory) => (
                      <div key={memory.id} className="memory-card-read">
                        <div className="card-header">
                          <span className="memory-id">#{typeof memory.id === 'string' ? memory.id.slice(0, 8) : memory.id}</span>
                          <span className="memory-date">
                            {new Date(memory.created_at).toLocaleDateString()}
                          </span>
                        </div>
                        <div className="card-content">
                          <HighlightText text={memory.content} highlight={search} />
                        </div>
                        <div className="card-tags">
                          {memory.category && <span className="tag category">{memory.category}</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {relations.length > 0 && (
                  <div className="memory-section">
                    <h3>🔗 关联图谱数据 ({relations.length})</h3>
                    <div className="relations-list">
                      {relations.map((rel, idx) => (
                        <div key={idx} className="relation-item">
                          <span className="node source">{rel.source}</span>
                          <span className="arrow">── {rel.relationship} ──▶</span>
                          <span className="node target">{rel.target}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
