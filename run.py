import os
from dotenv import load_dotenv
load_dotenv()

from app import create_app, socketio

env = os.environ.get('FLASK_ENV', 'development')
app = create_app('production' if env == 'production' else 'development')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, debug=(env != 'production'), host='0.0.0.0', port=port)
