"""
SIRIAN VTUBE — VTube Studio API 연동
감정 상태 → 표정/파라미터 자동 제어
"""
import websocket, json, threading, time, logging
log = logging.getLogger("vtube")

VTS_URL = "ws://localhost:8001"
PLUGIN_NAME = "SirianAgent"
PLUGIN_DEV  = "D4rkScare"

# 감정 → 표정 파일 매핑
EMOTION_EXP = {
    "뿌듯":   "爱心眼",
    "즐거움": "星星眼",
    "빡침":   "脸黑",
    "걱정됨": "qwq",
    "집중":   "！！",
    "무관심": None,
    "neutral": None,
}

class VTubeConnector:
    def __init__(self):
        self.ws = None
        self.token = None
        self.connected = False
        self.current_emotion = "neutral"
        self._thread = None
        self._lock = threading.Lock()

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while True:
            try:
                self.ws = websocket.WebSocketApp(
                    VTS_URL,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close
                )
                self.ws.run_forever()
            except Exception as e:
                log.debug(f"VTS 연결 실패: {e}")
            time.sleep(5)

    def _send(self, data):
        try:
            if self.ws:
                self.ws.send(json.dumps(data))
        except: pass

    def _on_open(self, ws):
        log.info("VTube Studio 연결됨")
        # 인증 요청
        self._send({
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": "auth",
            "messageType": "AuthenticationTokenRequest",
            "data": {
                "pluginName": PLUGIN_NAME,
                "pluginDeveloper": PLUGIN_DEV
            }
        })

    def _on_message(self, ws, message):
        try:
            msg = json.loads(message)
            mtype = msg.get("messageType","")

            if mtype == "AuthenticationTokenResponse":
                self.token = msg["data"]["authenticationToken"]
                # 인증
                self._send({
                    "apiName": "VTubeStudioPublicAPI",
                    "apiVersion": "1.0",
                    "requestID": "auth2",
                    "messageType": "AuthenticationRequest",
                    "data": {
                        "pluginName": PLUGIN_NAME,
                        "pluginDeveloper": PLUGIN_DEV,
                        "authenticationToken": self.token
                    }
                })

            elif mtype == "AuthenticationResponse":
                if msg["data"]["authenticated"]:
                    self.connected = True
                    log.info("VTube Studio 인증 완료")
                else:
                    log.warning("VTube Studio 인증 실패")

        except Exception as e:
            log.debug(f"메시지 처리 오류: {e}")

    def _on_error(self, ws, error):
        log.debug(f"VTS 오류: {error}")

    def _on_close(self, ws, *args):
        self.connected = False
        log.debug("VTS 연결 끊김")

    def set_expression(self, exp_name: str, active: bool = True):
        """표정 파일 활성화/비활성화"""
        if not self.connected: return
        self._send({
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": "exp",
            "messageType": "ExpressionActivationRequest",
            "data": {
                "expressionFile": exp_name + ".exp3",
                "active": active
            }
        })

    def set_emotion(self, emotion: str):
        """감정 상태 → 표정 자동 적용"""
        if not self.connected: return
        if emotion == self.current_emotion: return

        # 이전 표정 비활성화
        prev_exp = EMOTION_EXP.get(self.current_emotion)
        if prev_exp:
            self.set_expression(prev_exp, False)

        # 새 표정 활성화
        new_exp = EMOTION_EXP.get(emotion)
        if new_exp:
            self.set_expression(new_exp, True)
            log.info(f"표정 변경: {emotion} → {new_exp}")

        self.current_emotion = emotion

    def trigger_hotkey(self, hotkey_id: str):
        """핫키 트리거"""
        if not self.connected: return
        self._send({
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": "hotkey",
            "messageType": "HotkeyTriggerRequest",
            "data": {"hotkeyID": hotkey_id}
        })

    def set_parameter(self, param_id: str, value: float):
        """파라미터 값 직접 설정"""
        if not self.connected: return
        self._send({
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": "param",
            "messageType": "InjectParameterDataRequest",
            "data": {
                "parameterValues": [
                    {"id": param_id, "value": value}
                ]
            }
        })

    def set_mouth_open(self, value: float):
        """입 열기 (TTS 연동)"""
        self.set_parameter("MouthOpen", value)

vtube = VTubeConnector()
