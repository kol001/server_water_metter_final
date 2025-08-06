from flask_socketio import emit

def init_websocket(socketio):
    @socketio.on("connect", namespace="/ws/water-level")
    def ws_connect_wl():
        emit("message", {"info": "connected water-level"})

    @socketio.on("connect", namespace="/ws/alerts")
    def ws_connect_alerts():
        emit("message", {"info": "connected alerts"})

    @socketio.on("connect", namespace="/ws/pump_action")
    def ws_connect_pump():
        emit("message", {"info": "connected pump_action"})

    @socketio.on_error("/ws/pump_action")
    def error_handler(e):
        print(f"[WebSocket] Erreur dans /ws/pump_action : {str(e)}")    

    @socketio.on("connect", namespace="/ws/timer")
    def ws_connect_timer():
        emit("message", {"info": "connected timer"})

    @socketio.on("kit_status", namespace="/ws/kit")
    def ws_kit_status(data):
        emit("kit_status", {"data": data}, broadcast=True)