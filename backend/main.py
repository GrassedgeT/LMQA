from flask import Flask, jsonify, request
from flask_cors import CORS
import json
import os

app = Flask(__name__)
# 配置CORS以允许跨域请求
CORS(app)

# 简单的数据存储（在实际应用中应使用数据库）
DATA_FILE = 'todos.json'

def load_todos():
    """加载待办事项数据"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_todos(todos):
    """保存待办事项数据"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(todos, f, ensure_ascii=False, indent=2)

# 初始化数据文件（如果不存在）
if not os.path.exists(DATA_FILE):
    save_todos([])

@app.route("/")
def hello_world():
    return "<p>Hello, World!</p>"

# GET - 获取所有待办事项
@app.route("/api/todos", methods=["GET"])
def get_todos():
    todos = load_todos()
    return jsonify(todos)

# POST - 创建新的待办事项
@app.route("/api/todos", methods=["POST"])
def create_todo():
    todos = load_todos()
    new_todo = request.get_json()
    
    # 验证输入数据
    if not new_todo or 'text' not in new_todo:
        return jsonify({'error': '缺少必需的字段: text'}), 400
    
    # 添加新待办事项
    todo_id = len(todos) + 1
    todo = {
        'id': todo_id,
        'text': new_todo['text'],
        'completed': False
    }
    todos.append(todo)
    save_todos(todos)
    
    return jsonify(todo), 201

# PUT - 更新待办事项
@app.route("/api/todos/<int:todo_id>", methods=["PUT"])
def update_todo(todo_id):
    todos = load_todos()
    
    # 查找待办事项
    todo_index = None
    for i, todo in enumerate(todos):
        if todo['id'] == todo_id:
            todo_index = i
            break
    
    if todo_index is None:
        return jsonify({'error': '未找到指定的待办事项'}), 404
    
    # 更新待办事项
    update_data = request.get_json()
    if 'text' in update_data:
        todos[todo_index]['text'] = update_data['text']
    if 'completed' in update_data:
        todos[todo_index]['completed'] = update_data['completed']
    
    save_todos(todos)
    return jsonify(todos[todo_index])

# DELETE - 删除待办事项
@app.route("/api/todos/<int:todo_id>", methods=["DELETE"])
def delete_todo(todo_id):
    todos = load_todos()
    
    # 查找并删除待办事项
    todo_index = None
    for i, todo in enumerate(todos):
        if todo['id'] == todo_id:
            todo_index = i
            break
    
    if todo_index is None:
        return jsonify({'error': '未找到指定的待办事项'}), 404
    
    deleted_todo = todos.pop(todo_index)
    save_todos(todos)
    
    return jsonify(deleted_todo)

if __name__ == '__main__':
    app.run(debug=True)