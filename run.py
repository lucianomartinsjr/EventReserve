import eventlet
eventlet.monkey_patch(socket=True, select=True)

from app import app, socketio

if __name__ == '__main__':
    socketio.run(app, 
        debug=True,
        host='0.0.0.0',
        port=5000,
        log_output=True,
        use_reloader=False
    )