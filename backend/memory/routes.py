
from flask import Blueprint, request, jsonify
from .manager import MemoryManager

memory_bp = Blueprint('memory', __name__, url_prefix='/api/memory')

# Initialize Manager (lazy load or on module import)
memory_manager = MemoryManager()

@memory_bp.route('/add', methods=['POST'])
def add_memory():
    data = request.json
    content = data.get('content')
    user_id = data.get('user_id')
    run_id = data.get('run_id') # Optional
    metadata = data.get('metadata') # Optional

    if not content or not user_id:
        return jsonify({"error": "content and user_id are required"}), 400

    try:
        result = memory_manager.add_memory(content, user_id, run_id, metadata)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@memory_bp.route('/search', methods=['POST'])
def search_memories():
    data = request.json
    query = data.get('query')
    user_id = data.get('user_id')
    run_id = data.get('run_id') # Optional
    limit = data.get('limit', 5)

    if not query or not user_id:
        return jsonify({"error": "query and user_id are required"}), 400

    try:
        results = memory_manager.search_memories(query, user_id, run_id, limit)
        return jsonify(results), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@memory_bp.route('/all', methods=['GET'])
def get_all_memories():
    user_id = request.args.get('user_id')
    run_id = request.args.get('run_id') # Optional
    limit = int(request.args.get('limit', 100))

    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    try:
        results = memory_manager.get_memories(user_id, run_id, limit)
        return jsonify(results), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@memory_bp.route('/update/<memory_id>', methods=['PUT'])
def update_memory(memory_id):
    data = request.json
    new_data = data.get('text') # Mem0 expects 'data' often implies text content for update

    if not new_data:
        return jsonify({"error": "text is required to update memory"}), 400

    try:
        result = memory_manager.update_memory(memory_id, new_data)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@memory_bp.route('/delete/<memory_id>', methods=['DELETE'])
def delete_memory(memory_id):
    try:
        result = memory_manager.delete_memory(memory_id)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@memory_bp.route('/delete-all', methods=['DELETE'])
def delete_all_memories():
    user_id = request.args.get('user_id')
    run_id = request.args.get('run_id')

    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    try:
        result = memory_manager.delete_all_memories(user_id, run_id)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
