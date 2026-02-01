import sqlite3
import logging
from datetime import datetime, timezone
from typing import List
from flask import current_app

logger = logging.getLogger(__name__)

def get_db_path():
    return current_app.config['DATABASE']

def init_db(app=None):
    """初始化数据库表"""
    # If app is provided, use its config, otherwise use current_app
    db_path = app.config['DATABASE'] if app else get_db_path()
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # 用户表
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 对话表
    c.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT,
            message_count INTEGER DEFAULT 0,
            last_message_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    # 消息表
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
    ''')
    
    # 记忆表
    c.execute('''
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            conversation_id INTEGER,
            mem0_memory_id TEXT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            memory_type TEXT,
            category TEXT,
            tags TEXT,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
    ''')
    
    # 用户模型配置表
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_model_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            model_name TEXT NOT NULL,
            api_key TEXT NOT NULL,
            base_url TEXT,
            is_default INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id, provider, model_name)
        )
    ''')
    
    # 数据库迁移：为memories表添加conversation_id字段
    try:
        # 检查memories表是否已有conversation_id字段
        c.execute("PRAGMA table_info(memories)")
        columns = c.fetchall()
        column_names = [col[1] for col in columns]

        if 'conversation_id' not in column_names:
            logger.info('为memories表添加conversation_id字段')
            c.execute('ALTER TABLE memories ADD COLUMN conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE')
    except Exception as e:
        logger.error(f'数据库迁移失败: {str(e)}')
        # 不抛出异常，继续运行

    conn.commit()
    conn.close()

def convert_timestamp_to_iso(timestamp_str: str) -> str:
    """将 SQLite 时间戳转换为 ISO 8601 格式（UTC）"""
    if not timestamp_str:
        return timestamp_str
    try:
        # SQLite 的 CURRENT_TIMESTAMP 返回格式: 'YYYY-MM-DD HH:MM:SS' (UTC)
        # 转换为 ISO 8601 格式并添加 UTC 时区标识
        dt = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        # 假设数据库存储的是 UTC 时间，转换为 UTC 时区对象
        dt_utc = dt.replace(tzinfo=timezone.utc)
        # 返回 ISO 8601 格式字符串，带 'Z' 后缀表示 UTC
        return dt_utc.isoformat().replace('+00:00', 'Z')
    except (ValueError, AttributeError, TypeError):
        # 如果解析失败，返回原值
        return timestamp_str

def execute_query(query: str, params: tuple = ()) -> List[sqlite3.Row]:
    """执行查询"""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        c = conn.cursor()
        c.execute(query, params)
        results = c.fetchall()
        # 转换所有时间戳字段为 ISO 8601 格式
        converted_results = []
        for row in results:
            row_dict = dict(row)
            # 转换所有可能的时间戳字段
            timestamp_fields = ['created_at', 'updated_at', 'last_message_at', 'edited_at']
            for field in timestamp_fields:
                if field in row_dict and row_dict[field]:
                    row_dict[field] = convert_timestamp_to_iso(row_dict[field])
            # 创建一个类似 Row 的对象，保持原有接口
            class RowLike:
                def __init__(self, data):
                    self._data = data
                    for key, value in data.items():
                        setattr(self, key, value)
                def __getitem__(self, key):
                    return self._data[key]
                def __contains__(self, key):
                    return key in self._data
                def keys(self):
                    return self._data.keys()
                def get(self, key, default=None):
                    return self._data.get(key, default)
            converted_results.append(RowLike(row_dict))
        return converted_results if converted_results else results
    except Exception as e:
        logger.error(f'数据库查询错误: {str(e)}, SQL: {query}, Params: {params}')
        raise
    finally:
        conn.close()

def execute_update(query: str, params: tuple = ()) -> int:
    """执行更新，返回最后插入的ID"""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        c = conn.cursor()
        c.execute(query, params)
        conn.commit()
        return c.lastrowid
    except Exception as e:
        conn.rollback()
        logger.error(f'数据库更新错误: {str(e)}, SQL: {query}, Params: {params}')
        raise
    finally:
        conn.close()
