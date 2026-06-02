import http.server
import socketserver
import json
import os
import urllib.parse
from http import HTTPStatus

PORT = 8000
KEYWORDS_FILE = 'job_keywords.json'
TRAINING_DATA_FILE = 'training_data.json'

import subprocess

class JobOfferHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        parsed_path = urllib.parse.urlparse(self.path)
        
        if parsed_path.path == '/keywords':
            self.handle_keywords_update()
        elif parsed_path.path == '/feedback':
            self.handle_feedback()
        elif parsed_path.path == '/reanalyze':
            self.handle_reanalyze()
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        
        if parsed_path.path == '/keywords':
            self.handle_get_keywords()
        elif parsed_path.path == '/feedback':
            self.handle_get_feedback()
        else:
            # Default behavior for static files
            super().do_GET()

    def handle_get_keywords(self):
        try:
            with open(KEYWORDS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(data).encode('utf-8'))
        except Exception as e:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(e))
            
    def handle_get_feedback(self):
        try:
            # Load existing training data
            if os.path.exists(TRAINING_DATA_FILE):
                with open(TRAINING_DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                data = []
                
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(data).encode('utf-8'))
        except Exception as e:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(e))

    def handle_keywords_update(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        try:
            new_keywords = json.loads(post_data.decode('utf-8'))
            with open(KEYWORDS_FILE, 'w', encoding='utf-8') as f:
                json.dump(new_keywords, f, ensure_ascii=False, indent=2)
            
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status": "success"}')
        except Exception as e:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(e))

    def handle_reanalyze(self):
        try:
            # 1. Run the Training script first (Continuous Learning)
            print("LEARN: Iniciando fase de entrenamiento...")
            train_result = subprocess.run(['python', 'train_model.py'], capture_output=True, text=True)
            if train_result.returncode != 0:
                print(f"LEARN ERROR: {train_result.stderr}")
            else:
                print(train_result.stdout)
                
            # 2. Run the detection script
            print("INFO: Ejecutando re-análisis completo...")
            result = subprocess.run(['python', 'detect_jobs.py'], capture_output=True, text=True)
            
            if result.returncode == 0:
                print("SUCCESS: Procesamiento finalizado.")
                self.send_response(HTTPStatus.OK)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"status": "success", "message": "Training and Analysis complete"}')
            else:
                print(f"CRITICAL: Error en detección: {result.stderr}")
                self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Script error: {result.stderr}")
        except Exception as e:
            print(f"CRITICAL: Servidor falló: {e}")
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(e))

    def handle_feedback(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        try:
            feedback = json.loads(post_data.decode('utf-8'))
            
            if os.path.exists(TRAINING_DATA_FILE):
                with open(TRAINING_DATA_FILE, 'r', encoding='utf-8') as f:
                    try:
                        training_data = json.load(f)
                    except json.JSONDecodeError:
                        training_data = []
            else:
                training_data = []
            
            existing_idx = -1
            for i, item in enumerate(training_data):
                if item.get('text') == feedback.get('text') and item.get('author') == feedback.get('author'):
                    existing_idx = i
                    break
            
            if existing_idx >= 0:
                # Update counters
                item = training_data[existing_idx]
                # Reset or Migrate older schema if needed
                if 'votes' not in item:
                    # Migrate old boolean 'is_offer' to counter
                    old_vote = item.get('is_offer', False)
                    item['votes'] = {'yes': 1 if old_vote else 0, 'no': 1 if not old_vote else 0}
                
                # Increment based on new feedback
                if feedback.get('is_offer'):
                    item['votes']['yes'] += 1
                else:
                    item['votes']['no'] += 1
                    
                # Update 'is_offer' based on majority (for backward compatibility with detection script)
                item['is_offer'] = item['votes']['yes'] > item['votes']['no']
                item['timestamp'] = feedback.get('timestamp') # Update last activity
                
                training_data[existing_idx] = item
            else:
                # New entry
                new_item = {
                    'text': feedback.get('text'),
                    'author': feedback.get('author'),
                    'is_offer': feedback.get('is_offer'),
                    'timestamp': feedback.get('timestamp'),
                    'votes': {
                        'yes': 1 if feedback.get('is_offer') else 0,
                        'no': 1 if not feedback.get('is_offer') else 0
                    }
                }
                training_data.append(new_item)
            
            with open(TRAINING_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(training_data, f, ensure_ascii=False, indent=2)
                
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status": "saved"}')
        except Exception as e:
            print(f"Error saving feedback: {e}")
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(e))

    def handle_reanalyze(self):
        try:
            # 1. Run the Training script first (Continuous Learning)
            print("LEARN: Iniciando fase de entrenamiento...")
            train_result = subprocess.run(['python', 'train_model.py'], capture_output=True, text=True)
            if train_result.returncode != 0:
                print(f"LEARN ERROR: {train_result.stderr}")
            else:
                print(train_result.stdout)
                
            # 2. Run the detection script
            print("INFO: Ejecutando re-análisis completo...")
            result = subprocess.run(['python', 'detect_jobs.py'], capture_output=True, text=True)
            
            if result.returncode == 0:
                print("SUCCESS: Procesamiento finalizado.")
                self.send_response(HTTPStatus.OK)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"status": "success", "message": "Training and Analysis complete"}')
            else:
                print(f"CRITICAL: Error en detección: {result.stderr}")
                self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Script error: {result.stderr}")
        except Exception as e:
            print(f"CRITICAL: Servidor falló: {e}")
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(e))

print(f"Server backend running at http://localhost:{PORT}")
print(f"API Endpoints available:")
print(f" - GET/POST /keywords")
print(f" - POST /feedback")

with socketserver.TCPServer(("", PORT), JobOfferHandler) as httpd:
    httpd.serve_forever()
