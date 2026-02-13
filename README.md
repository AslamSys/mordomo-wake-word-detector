# 🎯 Wake Word Detector

**Container:** `wake-word-detector`  
**Ecossistema:** Mordomo  
**Posição no Fluxo:** Segundo componente - ativação do sistema

---

## 🚀 Quick Start

### 1️⃣ Treinar modelo "ASLAM"

```powershell
# Ative o ambiente
.venv\Scripts\Activate.ps1

# Grave amostras positivas (100+)
python gravar_amostras_aslam.py

# Grave amostras negativas (200+)
python gravar_amostras_aslam.py

# Treine o modelo
python treinar_modelo_aslam.py
```

📖 **Guia completo:** [TREINAR_ASLAM.md](./TREINAR_ASLAM.md)

### 2️⃣ Executar serviço

```powershell
# Configure o .env
cp .env.example .env
# Edite: WAKE_WORD_MODEL_PATH=models/aslam_v0.1.onnx

# Execute
docker-compose up
```

---

## 📋 Propósito

**Detector de ativação passivo** - Escuta continuamente o áudio do VAD via ZeroMQ e **apenas sinaliza** via NATS quando detecta "ASLAM". **NÃO processa, NÃO armazena, NÃO repassa áudio** - funciona como uma **flag/gatilho** puro.

---

## 🎯 Responsabilidades

- ✅ **Consumir áudio do VAD** via ZeroMQ SUB (passivo, não interfere)
- ✅ **Detectar wake word "ASLAM"** com alta precisão
- ✅ **Publicar evento simples no NATS** quando detectado (apenas metadado)
- ✅ **Implementar cooldown** para evitar re-detecção durante conversação ativa
- ✅ **Escutar eventos de sessão** para saber quando reativar detecção
- ✅ Minimizar falsos positivos e negativos
- ✅ Low power consumption (sempre ativo, < 3% CPU)

**O que NÃO faz:**
- ❌ NÃO repassa áudio para outros componentes
- ❌ NÃO processa o áudio (só detecta)
- ❌ NÃO guarda histórico
- ❌ NÃO interfere no fluxo do VAD

---

## 🔄 Estados do Wake Word Detector

```
┌─────────────────────────────────────────────┐
│  IDLE (Detectando)                          │
│  - Escuta áudio continuamente               │
│  - OpenWakeWord ativo                       │
│  - Pronto para detectar "ASLAM"             │
└──────────────┬──────────────────────────────┘
               ↓ (detectou "ASLAM")
┌─────────────────────────────────────────────┐
│  SUPPRESSED (Suprimido)                     │
│  - Ignora frames de áudio                   │
│  - Deixa conversa fluir                     │
│  - Aguarda evento: conversation.ended       │
└──────────────┬──────────────────────────────┘
               ↓ (recebeu conversation.ended)
┌─────────────────────────────────────────────┐
│  IDLE (volta a detectar IMEDIATAMENTE)      │
└─────────────────────────────────────────────┘
```

**Características:**
- ✅ **Event-driven**: Sem timeouts arbitrários
- ✅ **Responsivo**: Volta imediatamente após conversa
- ✅ **Simples**: Apenas 2 estados
- ✅ **Observável**: Se travar em SUPPRESSED, problema é detectável

---

## 🔮 Arquitetura Futura (ESP32 Offloading)

**Status:** Planejado (Roadmap)

No futuro, com a introdução de satélites ESP32-S3:
1.  A detecção da Wake Word ("Mordomo" ou "ASLAM") será feita **no hardware do ESP32** (Edge AI).
2.  O ESP32 enviará um sinal de trigger junto com o áudio.
3.  Este container (`wake-word-detector`) poderá ser:
    *   **Desativado:** Se confiarmos 100% no ESP32.
    *   **Validador:** Continuar rodando para confirmar a detecção do ESP32 (Second Stage Wake Word) e evitar falsos positivos do hardware mais simples.

**Por enquanto:** Este container é o **único** responsável pela detecção, rodando `OpenWakeWord` no servidor central.

---

## 🔧 Tecnologias

**Linguagem:** Python

**Principal:** OpenWakeWord (Open Source)
- 100% open source (Apache 2.0)
- Zero dependências de cloud/API
- Backend: **PyTorch** (C++ libtorch nativo)
- Inference: ONNX Runtime (C++ otimizado)

**Performance:** Modelo roda em C++ (ONNX Runtime), Python wrapper ~2ms overhead
- Sem Access Keys necessárias
- Otimizado para ARM
- Baixíssimo consumo de CPU
- Modelos customizáveis
- Suporta múltiplas wake words
- Baseado em TensorFlow Lite / ONNX

**Por que OpenWakeWord:**
- ✅ Sem risco de bloqueio de conta
- ✅ Totalmente offline
- ✅ Comunidade ativa
- ✅ Performance competitiva
- ✅ Treina modelos localmente

---

## 📊 Especificações

```yaml
Input Audio:
  Sample Rate: 16000 Hz
  Channels: 1 (mono)
  Bit Depth: 16-bit
  Chunk Size: 1280 samples (80ms)

Detection:
  Wake Word: "alexa" (ou customizada)
  Threshold: 0.5 (0.0-1.0 - quanto maior, mais conservador)
  Suppression: Event-based (conversation.ended)
  Inference: ONNX (ou TFLite)
  
Performance:
  CPU Usage: < 3% (1 core)
  RAM Usage: ~ 50-100 MB
  Latency: < 100 ms
```

---

## 🔌 Interfaces
```python
# 1. ZeroMQ SUB - ESCUTA o VAD (não interfere no fluxo)
endpoint: "tcp://audio-capture-vad:5555"
topic: "audio.raw"

# Recebe frames contínuos de 30ms
# Processa localmente com OpenWakeWord (quando não em SUPPRESSED)
# NÃO repassa áudio para ninguém

# 2. NATS SUB - Escuta eventos de sessão (para controle de cooldown)
subject: "conversation.started"  # → entra em cooldown
subject: "conversation.ended"    # → volta a detectar
```

### Output (Flag/Evento Apenas)
```python
# NATS Event - SINALIZAÇÃO pura (sem áudio)
subject: "wake_word.detected"
payload: {
  "timestamp": 1732723200.123,       # quando detectou
  "confidence": 0.85,                 # confiança (0.0-1.0)
  "keyword": "aslam",                 # palavra detectada
  "audio_snippet": "<base64 1s>",    # opcional: 1s de contexto
  "sequence": 12345,                  # frame do VAD onde detectou
  "session_id": "uuid"                # ID da nova sessão criada
}

# Este evento dispara PROCESSAMENTO PARALELO:
#  ├─→ Speaker Verification (200ms) [GATE]
#  ├─→ Whisper ASR (inicia buffering)
#  ├─→ Speaker ID/Diarization (inicia buffering)
#  ├─→ Conversation Manager (cria sessão)
#  ├─→ Dashboard UI (feedback visual)
#  └─→ Wake Word Detector (entra em SUPPRESSED)
```
IMPORTANTE: Áudio flui direto do VAD para todos consumidores.
Wake Word apenas SINALIZA quando sistema deve começar a processar.
```

---

## 🔧 Tecnologias

**Principal:** Porcupine (Picovoice)
- Otimizado para ARM
- Baixíssimo consumo de CPU
- Modelo customizável
- Suporta múltiplas wake words

**Alternativas:**
## 🔌 Interfaces

### Input (Consumo Passivo)
```python
# ZeroMQ SUB - ESCUTA o VAD (não interfere no fluxo)
endpoint: "tcp://audio-capture-vad:5555"
topic: "audio.raw"

# Recebe frames contínuos de 30ms
# Processa localmente com Porcupine
# NÃO repassa áudio para ninguém
```

### Output (Flag/Evento Apenas)
```python
# NATS Event - SINALIZAÇÃO pura (sem áudio)
subject: "wake_word.detected"
payload: {
  "timestamp": 1732723200.123,       # quando detectou
  "confidence": 0.85,                 # confiança (0.0-1.0)
  "keyword": "aslam",                 # palavra detectada
  "audio_snippet": "<base64 1s>",    # opcional: 1s de contexto
  "sequence": 12345                   # frame do VAD onde detectou
}

# Quem escuta este evento:
# - Speaker Verification (próximo no pipeline)
# - Conversation Manager (para criar sessão)
# - Dashboard UI (para feedback visual)
```

**Fluxo de Áudio Real:**
```
VAD → Speaker Verification (direto via ZeroMQ)
VAD → Whisper STT (direto via ZeroMQ)
VAD → [futuros consumidores] (direto via ZeroMQ)

Wake Word NÃO está no caminho do áudio!
Ele apenas observa e sinaliza.
```alse Negative Rate: < 5%
  
Performance:
  CPU Usage: < 3% (1 core)
  RAM Usage: ~ 30 MB
  Latency: < 50 ms
```

---

## 🔌 Interfaces

### Input
```python
# ZeroMQ SUB
endpoint: "tcp://audio-capture-vad:5555"
topic: "audio.raw"
```

### Output
```python
# NATS Event
subject: "wake_word.detected"
payload: {
  "timestamp": 1732723200.123,
  "confidence": 0.85,
  "keyword": "aslam",
  "audio_snippet": "<base64 encoded 1s audio>"
}
```

---

## ⚙️ Configuração

```yaml
wake_word:
  keyword: "aslam"
  sensitivity: 0.7
  model_path: "/models/aslam_porcupine.ppn"

cooldown:
  strategy: "hybrid"  # "fixed" | "event-based" | "hybrid"
  timeout_seconds: 60  # timeout máximo (segurança)
  listen_for_events: true  # escutar conversation.ended
  
input:
  zeromq_endpoint: "tcp://audio-capture-vad:5555"
  
## 📈 Métricas

```python
# Detecções
wake_word_detections_total

# Estado atual (0 = IDLE, 1 = SUPPRESSED)
wake_word_suppressed  # gauge

# Performance
wake_word_confidence_avg
wake_word_processing_latency_seconds

# Duração de supressão (tempo que ficou esperando conversation.ended)
wake_word_suppression_duration_seconds  # histogram

# Eventos recebidos
wake_word_conversation_ended_events_total
```e_word_detections_total
wake_word_cooldown_active  # 0 ou 1 (gauge)
wake_word_false_positives_total  # Estimado
wake_word_confidence_avg
wake_word_processing_latency_seconds
wake_word_cooldown_duration_seconds  # histogram
```
```python
class WakeWordDetector:
    def __init__(self):
        self.state = "IDLE"  # IDLE | COOLDOWN
        self.cooldown_until = None
        self.current_session_id = None
        
    async def process_audio(self, audio_frame):
        # Só detecta se estiver em IDLE
        if self.state == "COOLDOWN":
            return
            
        # Processa com Porcupine
        keyword_detected = porcupine.process(audio_frame)
        
        if keyword_detected:
            await self.on_wake_detected()
    
    async def on_wake_detected(self):
        # Publica evento
        session_id = uuid.uuid4()
        await nats.publish("wake_word.detected", {
            "timestamp": time.time(),
            "session_id": session_id
        })
        
        # Entra em cooldown
        self.state = "COOLDOWN"
        self.current_session_id = session_id
        self.cooldown_until = time.time() + 60  # max 60s
        
    async def on_conversation_ended(self, msg):
        # Escuta NATS: conversation.ended
        if msg.session_id == self.current_session_id:
            self.state = "IDLE"
            self.cooldown_until = None
            
    async def check_timeout(self):
        # Segurança: se passou 60s, volta pro IDLE
        if self.state == "COOLDOWN":
            if time.time() > self.cooldown_until:
                self.state = "IDLE"
```

---

## 📈 Métricas

```python
wake_word_detections_total
wake_word_false_positives_total  # Estimado
wake_word_confidence_avg
wake_word_processing_latency_seconds
## 🔗 Integração

**Recebe de:** 
- Audio Capture VAD (ZeroMQ SUB) - consome áudio passivamente

**Envia para:** 
- NATS (evento "wake_word.detected") - apenas flag/sinalização

**Quem reage ao evento:**
- Speaker Verification (pega evento + continua escutando VAD)
- Conversation Manager (inicia sessão)
- Dashboard UI (mostra LED verde "ouvindo")

**Áudio real flui:**
- VAD → Speaker Verification (direto)
- VAD → Whisper (direto)
- Wake Word **NÃO** está no caminho do áudio!

---

## 🔮 Roadmap & Futuro (Migração Precise)

Planejamos migrar do **OpenWakeWord** para o **Mycroft Precise** visando maior precisão em hardware embarcado e melhor ferramental de treinamento.

### Por que migrar?
- **Precisão Superior:** O Precise (RNN) tende a ser mais robusto para wake words customizadas ("Aslam") em ambientes ruidosos quando bem treinado.
- **Ferramental de Treino:** O projeto **Secret Sauce AI** fornece ferramentas excelentes (`wakeword-data-collector`, `precise-wakeword-model-maker`) para coleta e curadoria de datasets.
- **Performance:** Otimizado para rodar com < 5% de CPU em ARM.

### Plano de Ação
1. **Coleta de Dados:** Utilizar `wakeword-data-collector` para gravar milhares de amostras positivas/negativas no ambiente real.
2. **Treinamento:** Treinar modelo `.pb` usando `precise-wakeword-model-maker`.
3. **Benchmark:** Comparar falsos positivos/negativos entre OpenWakeWord (atual) e Precise.
4. **Implementação:** Substituir o engine atual pelo runner do Precise (Rust ou Python wrapper).

---

**Versão:** 1.1 (Updated 04/12/2025)
